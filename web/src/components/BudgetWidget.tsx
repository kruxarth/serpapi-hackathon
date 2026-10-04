import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { Mode } from '../types'

const MODE_TEXT: Record<Mode, string> = { live: 'Live', offline: 'Offline', demo: 'Demo' }
const MODE_TITLE: Record<Mode, string> = {
  live: 'Live: cache first, then SerpApi within the budget',
  offline: 'Offline: local cache only, nothing is fetched',
  demo: 'Demo: prepared synthetic examples, nothing is fetched',
}

export const useBudget = () => useQuery({ queryKey: ['budget'], queryFn: api.budget, refetchInterval: 30000 })

/** The header's one status area: run mode and searches left. */
export function StatusChip({ mode }: { mode: Mode | undefined }) {
  const b = useBudget().data
  if (!mode) return null
  const color = mode === 'live' ? 'var(--status-good)' : mode === 'offline' ? 'var(--muted)' : 'var(--accent)'
  return (
    <span className="status-chip" title={b?.note ?? MODE_TITLE[mode]}>
      <span className="pulse-dot" style={{ color }} aria-hidden />
      <strong>{MODE_TEXT[mode]}</strong>
      {b && mode !== 'demo' && (
        <>
          <span className="sep" />
          <span><strong className="num">{b.month_remaining}</strong> searches left</span>
        </>
      )}
    </span>
  )
}

/** Budget detail next to a cost estimate. */
export function BudgetDetail() {
  const b = useBudget().data
  if (!b) return null
  if (b.mode === 'demo') return <span className="muted">Demo mode spends no searches.</span>
  return (
    <div className="col" style={{ gap: 10 }}>
      <div className="row" style={{ alignItems: 'baseline', gap: 8 }}>
        <span className="big-num num">{b.month_remaining}</span>
        <span className="secondary">left this month</span>
      </div>
      <div className="secondary small"><strong className="num">{b.hour_remaining}</strong> left this hour · cap {b.per_analysis_cap} per analysis</div>
      {b.month_remaining === 0 && <div className="notice error small">The monthly search budget is used up. Offline and demo modes still work.</div>}
      {b.month_remaining > 0 && b.hour_remaining === 0 && (
        <div className="notice warn small">
          Hourly limit reached.{b.hour_resume_at && <> Searches free up at {new Date(b.hour_resume_at).toLocaleTimeString()}.</>}
        </div>
      )}
      {b.note && <div className="notice warn small">{b.note}</div>}
    </div>
  )
}
