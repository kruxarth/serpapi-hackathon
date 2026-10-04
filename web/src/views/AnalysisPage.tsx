import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Ban, Check, CircleAlert, Clock, Database, Pause } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { CountUp, EASE } from '../motion'
import { usePresentation } from '../presentation'
import type { AnalysisDetail, ProgressEvent } from '../types'
import { CandidatePicker } from './HomePage'
import { ReportView } from './ReportView'

const STAGES: { key: string; title: string; note: string; optional?: boolean }[] = [
  { key: 'resolving', title: 'Identify the place', note: 'Resolve the link to one listing' },
  { key: 'fetching_reviews', title: 'Fetch the newest reviews', note: 'The latest reviews, newest first' },
  { key: 'top_rated', title: 'Sample the highest-rated reviews', note: 'Only when the rating gap needs it', optional: true },
  { key: 'scoring', title: 'Score reviewers', note: 'Pick the most unusual accounts to open' },
  { key: 'expanding', title: 'Open reviewer histories', note: 'Every other place each account reviewed' },
  { key: 'building_graph', title: 'Build the co-review graph', note: 'Link accounts that share unrelated places' },
  { key: 'finding_groups', title: 'Find groups', note: 'Test each group against rings, trips and friends' },
]
const TERMINAL = ['done', 'cancelled', 'error', 'paused', 'needs_input']
const RUNNING = new Set(['queued', 'running', 'collected'])

export function AnalysisPage() {
  const { id = '' } = useParams()
  const pres = usePresentation()
  const q = useQuery({ queryKey: ['analysis', id, pres.on], queryFn: () => api.get(id, pres.on) })

  if (q.isLoading) return <div className="col" style={{ gap: 16 }}><div className="skeleton" style={{ height: 60, width: 480 }} /><div className="skeleton" style={{ height: 260 }} /></div>
  if (q.isError) return <div className="notice error"><CircleAlert size={16} />{(q.error as Error).message}</div>
  const a = q.data!
  if (a.status === 'done' && a.report) return <ReportView detail={a} />
  return <Progress detail={a} />
}

function Progress({ detail }: { detail: AnalysisDetail }) {
  const qc = useQueryClient()
  const pres = usePresentation()
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
      if (TERMINAL.includes(e.type)) {
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
  const round = expanding?.data?.round
  const reached = new Set(events.map((e) => e.type))
  const current = Math.max(-1, ...STAGES.map((s, i) => (reached.has(s.key) ? i : -1)))
  const finished = reached.has('done')

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

  const missing = Object.entries(detail.missing ?? {})
  return (
    <div>
      <Link to="/" className="row muted small" style={{ gap: 6, marginBottom: 22 }}><ArrowLeft size={14} /> All analyses</Link>
      <div className="progress-wrap">
        <div>
          <div className="eyebrow">Analysis {detail.id}</div>
          <h1 style={{ fontSize: '2.4rem', marginTop: 10, letterSpacing: '-0.04em' }}>
            {live ? (finished ? 'Writing the report…' : 'Reading the reviews') : STATUS_TITLE[detail.status] ?? detail.status}
          </h1>
          {detail.input && !pres.on && <p className="muted small mono" style={{ marginTop: 8, wordBreak: 'break-all' }}>{detail.input}</p>}

          {live && (
            <div className="panel" style={{ marginTop: 26, padding: '14px 18px' }}>
              <div className="stages" aria-live="polite">
                <div className="stage-rail">
                  <motion.div animate={{ height: `${finished ? 100 : (Math.max(0, current) / (STAGES.length - 1)) * 100}%` }} transition={{ duration: 0.8, ease: EASE }} style={{ height: 0 }} />
                </div>
                {STAGES.map((s, i) => {
                  const skipped = s.optional && !reached.has(s.key) && current > i
                  const state = finished || i < current ? 'done' : i === current ? 'active' : 'pending'
                  return (
                    <motion.div key={s.key} className={`stage ${skipped ? 'skipped' : state}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06, ease: EASE }}>
                      <div className="stage-node">
                        {state === 'active' && !skipped && <motion.span className="halo" animate={{ scale: [1, 1.5], opacity: [0.6, 0] }} transition={{ duration: 1.4, repeat: Infinity }} />}
                        <AnimatePresence mode="wait">
                          {state === 'done' && !skipped
                            ? <motion.span key="d" initial={{ scale: 0 }} animate={{ scale: 1 }} style={{ display: 'grid' }}><Check size={14} strokeWidth={3} /></motion.span>
                            : <span className="mono tiny">{i + 1}</span>}
                        </AnimatePresence>
                      </div>
                      <div>
                        <div className="stage-title">{s.title}</div>
                        <div className="muted small">{skipped ? 'Not needed for this listing' : s.note}</div>
                        {s.key === 'expanding' && total > 0 && state !== 'pending' && (
                          <div style={{ marginTop: 8, maxWidth: 360 }}>
                            <div className="bar-track"><motion.div className="bar-fill" animate={{ width: `${(100 * done) / total}%` }} transition={{ duration: 0.5, ease: EASE }} /></div>
                            <div className="muted tiny num" style={{ marginTop: 4 }}>{done} of {total} histories{round ? ` · round ${String(round)}` : ''}</div>
                          </div>
                        )}
                      </div>
                      <div />
                    </motion.div>
                  )
                })}
              </div>
              <AnimatePresence>
                {reached.has('early_stop') && (
                  <motion.div className="notice small" style={{ margin: '6px 6px 8px' }} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                    No ring-like pattern among the highest-priority reviewers, so round 2 was skipped to save searches.
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          <div className="col" style={{ gap: 14, marginTop: 22 }}>
            {detail.status === 'paused' && (
              <State icon={<Pause size={16} />} tone="warn" title="Paused: waiting for the hourly search limit.">
                {detail.paused?.resume_at && <>It can resume after {new Date(detail.paused.resume_at).toLocaleTimeString()}. </>}
                Everything fetched so far is cached; resuming requests nothing twice.
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="btn primary sm" disabled={busy} onClick={() => act(() => api.resume(detail.id))}>Resume</button>
                  <button className="btn sm" disabled={busy} onClick={() => act(() => api.cancel(detail.id))}>Cancel</button>
                </div>
              </State>
            )}
            {detail.status === 'needs_input' && (
              <State icon={<CircleAlert size={16} />} title="Several places match. Pick one:">
                <div style={{ marginTop: 12 }}>
                  <CandidatePicker candidates={detail.candidates} disabled={busy} onPick={(pick) => pick && act(() => api.resume(detail.id, pick))} />
                </div>
              </State>
            )}
            {detail.status === 'cancelled' && (
              <State icon={<Ban size={16} />} title="Cancelled.">
                What was fetched stays cached.
                <div className="row" style={{ marginTop: 12 }}><button className="btn sm" disabled={busy} onClick={() => act(() => api.resume(detail.id))}>Resume</button></div>
              </State>
            )}
            {detail.status === 'error' && (
              <State icon={<CircleAlert size={16} />} tone="error" title="The analysis stopped.">
                {detail.error}
                <div className="row" style={{ marginTop: 12 }}><button className="btn primary sm" disabled={busy} onClick={() => act(() => api.resume(detail.id))}>Try again</button></div>
              </State>
            )}
            {missing.length > 0 && (
              <State icon={<Database size={16} />} title="Not in the cache.">
                {missing.map(([k, v]) => `${k} (would cost ${v})`).join(', ')}. Switch to live mode to fetch it.
              </State>
            )}
            {error && <div className="notice error"><CircleAlert size={16} />{error}</div>}
            {live && <div><button className="btn ghost sm" disabled={busy} onClick={() => act(() => api.cancel(detail.id))}>Cancel analysis</button></div>}
          </div>
        </div>

        <aside className="col" style={{ gap: 18, paddingTop: 34 }}>
          <div className="panel pad">
            <div className="eyebrow">Searches used</div>
            <div className="big-num num" style={{ fontSize: '4rem', marginTop: 10 }}>
              <AnimatePresence mode="popLayout">
                <motion.span key={used} initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -24, opacity: 0 }} transition={{ duration: 0.35, ease: EASE }} style={{ display: 'inline-block' }}>
                  <CountUp value={used} duration={0.4} />
                </motion.span>
              </AnimatePresence>
            </div>
            <div className="muted small" style={{ marginTop: 6 }}>Cached data is reused; nothing is fetched twice.</div>
          </div>
          {live && (
            <div className="panel pad">
              <div className="eyebrow" style={{ marginBottom: 12 }}><Clock size={12} style={{ verticalAlign: -1 }} /> Live log</div>
              <div className="log">
                <AnimatePresence initial={false}>
                  {(events.length ? [...events].reverse().slice(0, 10) : [{ type: 'queued', message: 'Queued…', searches_used: 0, data: {} }]).map((e, i) => (
                    <motion.div key={`${events.length - i}-${e.type}`} layout initial={{ opacity: 0, y: -8 }} animate={{ opacity: i === 0 ? 1 : 0.7, y: 0 }}>
                      {e.message}
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

const STATUS_TITLE: Record<string, string> = {
  paused: 'Paused',
  needs_input: 'Which place did you mean?',
  cancelled: 'Cancelled',
  error: 'Something went wrong',
}

function State({ icon, title, tone, children }: { icon: ReactNode; title: string; tone?: 'warn' | 'error'; children: ReactNode }) {
  return (
    <motion.div className={`notice ${tone ?? ''}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ ease: EASE }}>
      {icon}
      <div style={{ flex: 1 }}><strong style={{ color: 'var(--ink)' }}>{title}</strong> {children}</div>
    </motion.div>
  )
}
