// The reviews behind a branch of the sieve: what the reader keeps, or what a sign set aside. Each card shows every
// sign the review carries with its evidence: the phrases an AI model quoted, the search phrase, and for copied text
// the review it matches, with the shared wording marked.

import { Bot, ChevronDown, Copy, User } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { day } from '../labels'
import { phraseSpan } from '../text'
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
  const marks = useMemo(() => [
    ...(r.ai?.verdict === 'ai_style' ? r.ai.cues : []),
    ...(r.generated_marker ? [r.generated_marker] : []),
  ], [r])
  const keyword = r.keyword_phrase ?? null
  const twins = useMemo(() => (r.copied_with ?? []).map((id) => report.reviews.find((x) => x.review_id === id)).filter((x): x is ReviewRow => !!x), [r, report])
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
        {text ? <Marked text={text} marks={marks} keyword={keyword} named={!r.signs?.includes('keyword_style')} /> : <span className="muted small">{presentation || report.pseudonymized ? 'Text hidden in presentation mode.' : 'No text, only stars.'}</span>}
      </div>
      {long && <button className="link-btn tiny" onClick={() => setOpen(!open)}>{open ? 'Show less' : 'Show all'}</button>}
      {r.signs?.includes('copied_text') && (
        <div className="twin">
          <div className="tiny muted row" style={{ gap: 6 }}><Copy size={12} />
            {twins.length ? `Near-identical to ${twins.length === 1 ? 'a review' : `${twins.length} reviews`} by another account here` : 'Near-identical to a review another account wrote about a different place'}
          </div>
          {twins.map((t) => (
            <div key={t.review_id} className="twin-text">
              <span className="tiny muted">{namer.reviewer(t.contributor_id)} · {day(t.day)}</span>
              <p>{t.text && text ? <Shared text={t.text} other={text} /> : <span className="muted">{presentation || report.pseudonymized ? 'Text hidden in presentation mode.' : 'No text.'}</span>}</p>
            </div>
          ))}
          {twins.length > 0 && text && <div className="tiny muted">Wording both reviews share is marked.</div>}
        </div>
      )}
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

const WORD = /[\p{L}\p{N}]+/gu

/** The text with every run of three or more words that also occurs in `other` marked. */
export function Shared({ text, other }: { text: string; other: string }) {
  const words = [...text.matchAll(WORD)]
  const theirs = [...other.matchAll(WORD)].map((m) => m[0].toLowerCase())
  const grams = new Set(theirs.slice(0, -2).map((_, i) => theirs.slice(i, i + 3).join(' ')))
  const lower = words.map((m) => m[0].toLowerCase())
  const hit = new Array(words.length).fill(false)
  for (let i = 0; i + 2 < words.length; i++) {
    if (grams.has(lower.slice(i, i + 3).join(' '))) hit[i] = hit[i + 1] = hit[i + 2] = true
  }
  const out: ReactNode[] = []
  let pos = 0
  let i = 0
  while (i < words.length) {
    if (!hit[i]) { i++; continue }
    let j = i
    while (j + 1 < words.length && hit[j + 1]) j++
    const s = words[i].index!
    const e = words[j].index! + words[j][0].length
    out.push(text.slice(pos, s), <mark key={s} className="shared">{text.slice(s, e)}</mark>)
    pos = e
    i = j + 1
  }
  out.push(text.slice(pos))
  return <>{out}</>
}

/** The text with each quoted phrase highlighted where it occurs (case-insensitive, first occurrence). A search
 * phrase is tinted as a warning sign, or neutral when it only names the business with its area (`named`). */
export function Marked({ text, marks, keyword, named }: { text: string; marks: string[]; keyword?: string | null; named?: boolean }) {
  const spans: [number, number, string][] = []
  const low = text.toLowerCase()
  for (const m of marks) {
    const i = low.indexOf(m.toLowerCase())
    if (i >= 0 && m) spans.push([i, i + m.length, 'cue'])
  }
  const k = keyword ? phraseSpan(text, keyword) : null
  if (k) spans.push([k[0], k[1], named ? 'keyword named' : 'keyword'])
  spans.sort((a, b) => a[0] - b[0])
  const out: ReactNode[] = []
  let pos = 0
  spans.forEach(([s, e, cls], k) => {
    if (s < pos) return
    out.push(text.slice(pos, s))
    out.push(<mark key={k} className={cls}>{text.slice(s, e)}</mark>)
    pos = e
  })
  out.push(text.slice(pos))
  return <>{out}</>
}
