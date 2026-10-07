// The reviews behind a branch of the sieve: what the reader keeps, or what a sign set aside. Each card shows every
// sign the review carries; the phrases an AI model quoted are highlighted where they occur in the text.

import { Bot, ChevronDown, User } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { day } from '../labels'
import type { Namer } from '../names'
import type { Report, ReviewRow, SignKey } from '../types'
import { type Branch, type SieveState, signTone } from './Sieve'
import { Stars } from './ui'

const PAGE = 12

export function BranchTabs({ report, state, selected, onSelect }: { report: Report; state: SieveState; selected: Branch; onSelect: (b: Branch) => void }) {
  const sieve = report.sieve!
  const tabs: Branch[] = ['kept', ...sieve.order.filter((k) => state.aside.has(k) && (state.groups[k]?.length ?? 0) > 0)]
  return (
    <div className="branch-tabs" role="tablist" aria-label="Reviews by branch">
      {tabs.map((b) => (
        <button key={b} role="tab" aria-selected={selected === b} className={`branch-tab ${selected === b ? 'on' : ''}`} onClick={() => onSelect(b)}
          style={b === 'kept' ? undefined : { ['--tone' as string]: signTone(b, sieve.signs[b]) }}>
          {b !== 'kept' && <i className="swatch" />}
          {b === 'kept' ? 'Kept' : `Set aside: ${sieve.signs[b].short}`}
          <span className="num muted">{state.groups[b]?.length ?? 0}</span>
        </button>
      ))}
    </div>
  )
}

export function ReviewList({ report, state, branch, namer, presentation }: {
  report: Report; state: SieveState; branch: Branch; namer: Namer; presentation: boolean
}) {
  const rows = state.groups[branch] ?? []
  const [shown, setShown] = useState(PAGE)
  const sieve = report.sieve!
  const intro = branch === 'kept'
    ? (state.keptCount === report.reviews.length
      ? 'Every review is kept. Set a sign aside above to filter.'
      : 'The reviews left after setting aside the signs you chose, newest first.')
    : sieve.signs[branch].explain
  return (
    <div>
      <p className="secondary small" style={{ margin: '0 0 16px', maxWidth: '78ch' }}>{intro}</p>
      {rows.length === 0 && <div className="empty-line">No reviews here.</div>}
      <div className="review-grid">
        {rows.slice(0, shown).map((r) => <ReviewItem key={`${branch}-${r.review_id}`} r={r} report={report} namer={namer} branch={branch} presentation={presentation} />)}
      </div>
      {rows.length > shown && (
        <div className="row" style={{ justifyContent: 'center', marginTop: 18 }}>
          <button className="btn sm" onClick={() => setShown((x) => x + PAGE * 2)}>
            <ChevronDown size={14} /> Show more ({rows.length - shown} left)
          </button>
        </div>
      )}
    </div>
  )
}

function ReviewItem({ r, report, namer, branch, presentation }: { r: ReviewRow; report: Report; namer: Namer; branch: Branch; presentation: boolean }) {
  const [open, setOpen] = useState(false)
  const sieve = report.sieve!
  const first = r.reviewer_reviews != null && r.reviewer_reviews <= 1
  const account = r.reviewer_reviews == null ? null : first ? 'No other reviews' : `${r.reviewer_reviews} reviews`
  const text = r.text ?? r.excerpt ?? null
  const long = (text?.length ?? 0) > 320
  const marks = useMemo(() => [...(r.ai?.verdict === 'ai_style' ? r.ai.cues : []), ...(r.generated_marker ? [r.generated_marker] : [])], [r])
  return (
    <article className={`review-item ${branch === 'kept' ? '' : 'aside'}`}>
      <header className="row" style={{ gap: 10 }}>
        <span className="avatar sm" aria-hidden><User size={14} /></span>
        <div className="col" style={{ minWidth: 0, flex: 1 }}>
          <strong className="small ellipsis">{namer.reviewer(r.contributor_id)}</strong>
          {account && <span className={`tiny ${first ? 'first-time' : 'muted'}`}>{account}</span>}
        </div>
        <div className="col" style={{ alignItems: 'flex-end' }}>
          <Stars rating={r.rating} />
          <span className="tiny muted">{day(r.day)}</span>
        </div>
      </header>
      <div className={`review-text ${long && !open ? 'clamped' : ''}`}>
        {text ? <Marked text={text} marks={marks} /> : <span className="muted small">{presentation || report.pseudonymized ? 'Text hidden in presentation mode.' : 'No text, only stars.'}</span>}
      </div>
      {long && <button className="link-btn tiny" onClick={() => setOpen(!open)}>{open ? 'Show less' : 'Show all'}</button>}
      {r.ai?.verdict === 'ai_style' && (
        <div className="ai-note tiny"><Bot size={13} /> An AI model thinks this reads as AI-written because of the highlighted phrases. An opinion, not proof.</div>
      )}
      {(r.signs?.length ?? 0) > 0 && (
        <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
          {r.signs!.map((s: SignKey) => (
            <span key={s} className={`sign-chip ${sieve.signs[s].strength} ${s === branch ? 'routed' : ''}`} title={sieve.signs[s].explain} style={{ ['--tone' as string]: signTone(s, sieve.signs[s]) }}>
              <i className="swatch" />{sieve.signs[s].short}
            </span>
          ))}
        </div>
      )}
    </article>
  )
}

/** The text with each quoted phrase highlighted where it occurs (case-insensitive, first occurrence). */
function Marked({ text, marks }: { text: string; marks: string[] }) {
  const spans: [number, number][] = []
  const low = text.toLowerCase()
  for (const m of marks) {
    const i = low.indexOf(m.toLowerCase())
    if (i >= 0 && m) spans.push([i, i + m.length])
  }
  spans.sort((a, b) => a[0] - b[0])
  const out: ReactNode[] = []
  let pos = 0
  spans.forEach(([s, e], k) => {
    if (s < pos) return
    out.push(text.slice(pos, s))
    out.push(<mark key={k} className="cue">{text.slice(s, e)}</mark>)
    pos = e
  })
  out.push(text.slice(pos))
  return <>{out}</>
}
