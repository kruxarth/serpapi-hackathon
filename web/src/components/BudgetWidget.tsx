import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export function BudgetWidget({ compact = false }: { compact?: boolean }) {
  const q = useQuery({ queryKey: ['budget'], queryFn: api.budget, refetchInterval: 30000 })
  if (q.isError || !q.data) return null
  const b = q.data
  if (b.mode === 'demo') return compact ? null : <span className="muted">Demo mode spends no searches.</span>
  const low = b.month_remaining === 0
  const hourLow = b.hour_remaining === 0
  const text = (
    <>
      <strong className="num">{b.month_remaining}</strong> searches left this month ·{' '}
      <strong className="num">{b.hour_remaining}</strong> this hour
    </>
  )
  if (compact) {
    return (
      <span className="pill" title={b.note ?? 'SerpApi searches remaining (the Account API check is free)'}>
        {text}
      </span>
    )
  }
  return (
    <div className="stack">
      <div>{text}</div>
      {low && <div className="notice error">The monthly search budget is used up. Offline and demo modes still work.</div>}
      {!low && hourLow && (
        <div className="notice warn">
          Hourly limit reached.{' '}
          {b.hour_resume_at && <>Searches free up at {new Date(b.hour_resume_at).toLocaleTimeString()}.</>}
        </div>
      )}
      {b.note && <div className="notice warn">{b.note}</div>}
    </div>
  )
}
