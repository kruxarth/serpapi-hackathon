import { useMemo, useState } from 'react'
import { BADGE_NAMES, day, fmt, LABEL_ORDER, LABEL_TEXT } from '../labels'
import type { Namer } from '../names'
import type { ClientRow, Label, Report, ReviewRow } from '../types'
import { Stars } from './ui'

export function ReviewsTable({ report, namer, selectedGroup }: { report: Report; namer: Namer; selectedGroup: string | null }) {
  const present = LABEL_ORDER.filter((l) => (report.label_counts[l] ?? 0) > 0)
  // "Not checked" is hidden by default: those reviewers' histories weren't fetched, so the row says nothing either way.
  const [shown, setShown] = useState<Set<Label>>(() => new Set(present.filter((l) => l !== 'not_checked')))
  const members = useMemo(
    () => new Set(selectedGroup ? report.groups.find((g) => g.group_id === selectedGroup)?.members ?? [] : []),
    [report, selectedGroup],
  )
  const inGroup = (r: ReviewRow) => r.contributor_id != null && members.has(r.contributor_id)
  const rows = report.reviews.filter((r) => shown.has(r.label) || inGroup(r)).sort((a, b) => Number(inGroup(b)) - Number(inGroup(a)))
  const flip = (l: Label) => {
    const next = new Set(shown)
    if (next.has(l)) next.delete(l)
    else next.add(l)
    setShown(next)
  }
  return (
    <div>
      <div className="row wrap" style={{ gap: 8, marginBottom: 14 }}>
        {present.map((l) => (
          <button key={l} className={`chip ${shown.has(l) ? 'on' : ''}`} onClick={() => flip(l)} aria-pressed={shown.has(l)}>
            <i className={`swatch ${l}`} /> {LABEL_TEXT[l]} <span className="num" style={{ opacity: 0.7 }}>{report.label_counts[l]}</span>
          </button>
        ))}
        <span className="muted small" style={{ marginLeft: 6 }}>"Not checked" is neutral: the reviewer's history wasn't fetched (budget).</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Reviewer</th><th>Rating</th><th>Date</th><th>Label</th><th>Signals</th><th>Text</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.review_id} className={inGroup(r) ? 'selected' : ''}>
                <td>
                  <div style={{ fontWeight: 560, whiteSpace: 'nowrap' }}>{namer.reviewer(r.contributor_id)}</div>
                  {r.reviewer_reviews != null && <div className="muted tiny">{r.reviewer_reviews} review{r.reviewer_reviews === 1 ? '' : 's'}</div>}
                </td>
                <td style={{ whiteSpace: 'nowrap' }}><Stars rating={r.rating} /></td>
                <td className="num small secondary" style={{ whiteSpace: 'nowrap' }}>{day(r.day)}</td>
                <td><span className="row small" style={{ gap: 7, whiteSpace: 'nowrap' }}><i className={`swatch ${r.label}`} />{LABEL_TEXT[r.label]}</span></td>
                <td><div className="row wrap" style={{ gap: 4 }}>{r.badges.map((b) => <span key={b} className="badge" title={b}>{BADGE_NAMES[b] ?? b}</span>)}</div></td>
                <td className="text-cell"><ReviewText r={r} /></td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="muted">No reviews with the selected labels.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ReviewText({ r }: { r: ReviewRow }) {
  const [open, setOpen] = useState(false)
  const long = (r.text?.length ?? 0) > 160
  return (
    <>
      {r.text
        ? <span>{open || !long ? r.text : `${r.text.slice(0, 160)}…`} {long && <button onClick={() => setOpen(!open)}>{open ? 'less' : 'more'}</button>}</span>
        : <span className="muted">text not included ({r.text_length ?? 0} characters)</span>}
      {r.generated_marker && <div><span className="badge" style={{ color: 'var(--label-suspicious)' }}>chatbot text: "{r.generated_marker}"</span></div>}
      {r.cluster && <div className="muted tiny">near-duplicate group {r.cluster}</div>}
      {r.stock_phrase && <div className="muted tiny">common stock phrase (not counted)</div>}
    </>
  )
}

export function ClientTable({ rows, namer }: { rows: ClientRow[]; namer: Namer }) {
  if (!rows.length) return <p className="muted">No shared places.</p>
  return (
    <div className="table-scroll" style={{ maxHeight: 420 }}>
      <table>
        <thead><tr><th>Place</th><th>Area</th><th>Type</th><th>Members</th><th>When</th><th>Avg rating</th><th>Distance</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.place_key}>
              <td><strong>{namer.place(r.place_key)}</strong>{r.core && <span className="chip accent" style={{ marginLeft: 8, height: 20 }}>core</span>}</td>
              <td>{r.area ?? '–'}</td>
              <td className="small secondary">{r.type ?? '–'}</td>
              <td className="small" title={r.members.map((m) => namer.reviewer(m)).join(', ')}>
                <strong className="num">{r.member_count}</strong> <span className="muted">{r.members.slice(0, 3).map((m) => namer.reviewer(m)).join(', ')}{r.members.length > 3 ? '…' : ''}</span>
              </td>
              <td className="num small secondary">{r.date_from ? `${day(r.date_from)} – ${day(r.date_to)}` : 'unknown'}</td>
              <td className="num">{fmt(r.avg_rating, 1)}★</td>
              <td className="num small secondary">{r.distance_km != null ? `${r.distance_km} km` : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
