import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { usePresentation } from '../presentation'
import type { AnalysisDetail, ProgressEvent } from '../types'
import { ReportView } from './ReportView'

const STAGES: [string, string][] = [
  ['resolving', 'Identify the place'],
  ['fetching_reviews', 'Fetch the newest reviews'],
  ['scoring', 'Score reviewers'],
  ['expanding', 'Fetch reviewer histories'],
  ['building_graph', 'Build the co-review graph'],
  ['finding_groups', 'Find groups'],
  ['done', 'Done'],
]
const RUNNING = new Set(['queued', 'running', 'collected'])

export function AnalysisPage() {
  const { id = '' } = useParams()
  const pres = usePresentation()
  const q = useQuery({ queryKey: ['analysis', id, pres.on], queryFn: () => api.get(id, pres.on) })

  if (q.isLoading) return <p className="muted">Loading…</p>
  if (q.isError) return <div className="notice error">{(q.error as Error).message}</div>
  const a = q.data!
  if (a.status === 'done' && a.report) return <ReportView detail={a} />
  return <Progress detail={a} />
}

function Progress({ detail }: { detail: AnalysisDetail }) {
  const qc = useQueryClient()
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const live = RUNNING.has(detail.status)

  useEffect(() => {
    if (!live) return
    const es = new EventSource(api.eventsUrl(detail.id))
    es.onmessage = (m) => {
      const e = JSON.parse(m.data) as ProgressEvent
      setEvents((prev) => [...prev, e])
      if (['done', 'cancelled', 'error', 'paused', 'needs_input'].includes(e.type)) {
        es.close()
        qc.invalidateQueries({ queryKey: ['analysis', detail.id] })
        qc.invalidateQueries({ queryKey: ['budget'] })
        qc.invalidateQueries({ queryKey: ['analyses'] })
      }
    }
    es.onerror = () => {
      es.close()
      qc.invalidateQueries({ queryKey: ['analysis', detail.id] })
    }
    return () => es.close()
  }, [detail.id, live, qc])

  const last = events[events.length - 1]
  const used = last?.searches_used ?? detail.searches_used
  const expanding = [...events].reverse().find((e) => e.type === 'expanding')
  const done = Number(expanding?.data?.done ?? 0)
  const total = Number(expanding?.data?.total ?? 0)
  const reached = new Set(events.map((e) => e.type))
  const stageIndex = Math.max(-1, ...STAGES.map(([k], i) => (reached.has(k) ? i : -1)))

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      setEvents([])
      await qc.invalidateQueries({ queryKey: ['analysis', detail.id] })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 820 }}>
      <Link to="/">← Back</Link>
      <section className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>Analysis {detail.id}</h2>
          <div className="spacer" />
          <span className="pill num">Searches used: <strong>{used}</strong></span>
        </div>
        {detail.input && <p className="muted small" style={{ wordBreak: 'break-all' }}>{detail.input}</p>}

        {live && (
          <>
            <ul className="progress-list" aria-live="polite">
              {STAGES.map(([key, text], i) => (
                <li key={key} className={i <= stageIndex ? '' : 'muted'}>
                  <span aria-hidden>{i < stageIndex ? '✓' : i === stageIndex ? '…' : '·'}</span>
                  {text}
                  {key === 'expanding' && total > 0 && (
                    <span className="muted small num"> — {done} of {total}</span>
                  )}
                </li>
              ))}
            </ul>
            {total > 0 && (
              <div className="bar" style={{ marginTop: 10 }}><div style={{ width: `${(100 * done) / total}%` }} /></div>
            )}
            {reached.has('early_stop') && (
              <p className="notice small">No ring-like pattern among the highest-priority reviewers, so round 2 was skipped to save searches.</p>
            )}
            <p className="small secondary">{last?.message ?? 'Queued…'}</p>
            <button className="btn" disabled={busy} onClick={() => act(() => api.cancel(detail.id))}>Cancel</button>
          </>
        )}

        {detail.status === 'paused' && (
          <div className="notice warn">
            <strong>Paused: waiting for the hourly search limit.</strong>
            {detail.paused?.resume_at && (
              <> It can resume after {new Date(detail.paused.resume_at).toLocaleTimeString()}.</>
            )}{' '}
            Everything fetched so far is cached; resuming requests nothing twice.
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn primary" disabled={busy} onClick={() => act(() => api.resume(detail.id))}>Resume</button>
              <button className="btn" disabled={busy} onClick={() => act(() => api.cancel(detail.id))}>Cancel</button>
            </div>
          </div>
        )}

        {detail.status === 'needs_input' && (
          <div className="notice">
            <strong>Several places match. Pick one:</strong>
            <table style={{ marginTop: 8 }}>
              <tbody>
                {detail.candidates.map((c) => (
                  <tr key={c.data_id ?? c.title}>
                    <td><strong>{c.title}</strong><div className="muted small">{c.address}</div></td>
                    <td>{c.type}</td>
                    <td>
                      <button className="btn small" disabled={busy || !c.data_id}
                        onClick={() => act(() => api.resume(detail.id, c.data_id ?? undefined))}>This one</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {detail.status === 'cancelled' && (
          <div className="notice">
            Cancelled. What was fetched stays cached.{' '}
            <button className="btn small" disabled={busy} onClick={() => act(() => api.resume(detail.id))}>Resume</button>
          </div>
        )}

        {detail.status === 'error' && (
          <div className="notice error">
            <strong>The analysis stopped.</strong> {detail.error}
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn small" disabled={busy} onClick={() => act(() => api.resume(detail.id))}>Try again</button>
            </div>
          </div>
        )}
        {Object.keys(detail.missing ?? {}).length > 0 && (
          <div className="notice small">
            Not in the cache: {Object.entries(detail.missing).map(([k, v]) => `${k} (would cost ${v})`).join(', ')}.
          </div>
        )}
        {error && <div className="notice error">{error}</div>}
      </section>
    </div>
  )
}
