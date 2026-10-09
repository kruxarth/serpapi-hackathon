import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Ban, Check, CircleAlert, Clock, Database, Pause } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Investigation, usePlayback } from '../components/Investigation'
import { EASE } from '../motion'
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
  const navigate = useNavigate()
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const live = RUNNING.has(detail.status)
  const { state, played, caughtUp } = usePlayback(events)

  useEffect(() => {
    if (!live) return
    const es = new EventSource(api.eventsUrl(detail.id))
    es.onmessage = (m) => {
      const e = JSON.parse(m.data) as ProgressEvent
      setEvents((prev) => [...prev, e])
      if (TERMINAL.includes(e.type)) es.close()
    }
    es.onerror = () => {
      es.close()
      qc.invalidateQueries({ queryKey: ['analysis', detail.id] })
    }
    return () => es.close()
  }, [detail.id, live, qc])

  // The report opens once the viewer has seen the investigation through, not the instant the backend finishes, and
  // a check that just finished opens on its walkthrough.
  const ended = played.find((e) => TERMINAL.includes(e.type))
  useEffect(() => {
    if (!ended || !caughtUp) return
    const t = window.setTimeout(() => {
      if (ended.type === 'done' && live) navigate(`/analysis/${detail.id}?story=1`, { replace: true })
      qc.invalidateQueries({ queryKey: ['analysis', detail.id] })
      qc.invalidateQueries({ queryKey: ['budget'] })
      qc.invalidateQueries({ queryKey: ['analyses'] })
    }, ended.type === 'done' ? 1600 : 0)
    return () => clearTimeout(t)
  }, [ended, caughtUp, detail.id, qc, live, navigate])

  const last = played[played.length - 1]
  const expanding = [...played].reverse().find((e) => e.type === 'expanding')
  const done = Number(expanding?.data?.done ?? 0)
  const total = Number(expanding?.data?.total ?? 0)
  const round = expanding?.data?.round
  const reached = new Set(played.map((e) => e.type))
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
        <div style={{ minWidth: 0 }}>
          <div className="muted">Analysis {detail.id}</div>
          <h1 className="progress-title">
            {live ? (finished ? 'Report ready' : STAGE_TITLE[last?.type ?? ''] ?? 'Investigating') : STATUS_TITLE[detail.status] ?? detail.status}
          </h1>
          {detail.input && !pres.on && <p className="muted small" style={{ marginTop: 8, wordBreak: 'break-all' }}>{detail.input}</p>}

          {(live || played.length > 0) && <div className="panel pad" style={{ marginTop: 26 }}><Investigation state={state} /></div>}

          <div className="col" style={{ gap: 14, marginTop: 22 }}>
            {detail.status === 'paused' && (
              <State icon={<Pause size={16} />} tone="warn" title="Paused: too many checks this hour.">
                {detail.paused?.resume_at && <>It can resume after {new Date(detail.paused.resume_at).toLocaleTimeString()}. </>}
                Everything fetched so far is kept; resuming picks up where it stopped.
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
              <State icon={<Database size={16} />} title="Not fetched yet.">
                {missing.map(([k]) => k).join(', ')}. The report uses what was already fetched; live mode fetches the rest.
              </State>
            )}
            {error && <div className="notice error"><CircleAlert size={16} />{error}</div>}
            {live && !finished && <div><button className="btn ghost sm" disabled={busy} onClick={() => act(() => api.cancel(detail.id))}>Cancel analysis</button></div>}
          </div>
        </div>

        <aside className="col" style={{ gap: 18, paddingTop: 34 }}>
          {live && <Stages reached={reached} current={current} finished={finished} done={done} total={total} round={round} />}
          {live && (
            <div className="panel pad">
              <div className="secondary row" style={{ marginBottom: 12, gap: 6 }}><Clock size={14} /> What it is doing</div>
              <div className="log">
                <AnimatePresence initial={false}>
                  {(played.length ? [...played].reverse().slice(0, 10) : [{ type: 'queued', message: 'Queued…', searches_used: 0, data: {} }]).map((e, i) => (
                    <motion.div key={`${played.length - i}-${e.type}`} layout initial={{ opacity: 0, y: -8 }} animate={{ opacity: i === 0 ? 1 : 0.7, y: 0 }}>
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

const STAGE_TITLE: Record<string, string> = {
  resolving: 'Finding the place',
  fetching_reviews: 'Reading the reviews',
  reviews_loaded: 'Reading the reviews',
  top_rated: 'Sampling the highest-rated reviews',
  scoring: 'Choosing who to look at',
  picks: 'Choosing who to look at',
  expanding: 'Opening reviewer histories',
  history: 'Opening reviewer histories',
  building_graph: 'Looking for shared places',
  links: 'Looking for shared places',
  early_stop: 'Looking for shared places',
  finding_groups: 'Testing groups',
  reading_texts: 'Reading the longer reviews',
}

/** The pipeline as a compact checklist beside the live view. */
function Stages({ reached, current, finished, done, total, round }: { reached: Set<string>; current: number; finished: boolean; done: number; total: number; round: unknown }) {
  return (
    <div className="panel" style={{ padding: '10px 14px' }}>
      <div className="stages compact" aria-live="polite">
        <div className="stage-rail">
          <motion.div animate={{ height: `${finished ? 100 : (Math.max(0, current) / (STAGES.length - 1)) * 100}%` }} transition={{ duration: 0.8, ease: EASE }} style={{ height: 0 }} />
        </div>
        {STAGES.map((s, i) => {
          const skipped = s.optional && !reached.has(s.key) && current > i
          const state = finished || i < current ? 'done' : i === current ? 'active' : 'pending'
          return (
            <div key={s.key} className={`stage ${skipped ? 'skipped' : state}`}>
              <div className="stage-node">
                {state === 'active' && !skipped && <motion.span className="halo" animate={{ scale: [1, 1.5], opacity: [0.6, 0] }} transition={{ duration: 1.4, repeat: Infinity }} />}
                {state === 'done' && !skipped ? <Check size={12} strokeWidth={3} /> : <span>{i + 1}</span>}
              </div>
              <div>
                <div className="stage-title">{s.title}</div>
                {s.key === 'expanding' && total > 0 && state === 'active' && (
                  <div className="muted tiny num">{done} of {total}{round ? `, round ${String(round)}` : ''}</div>
                )}
              </div>
            </div>
          )
        })}
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
