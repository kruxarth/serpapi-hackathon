import { useMemo, useState } from 'react'
import { fmt, LABEL_TEXT } from '../labels'
import type { Namer } from '../names'
import type { ClientRow, Report } from '../types'

const BADGE_NAMES: Record<string, string> = {
  A1: 'Thin profile', A2: 'Rating monotony', A3: 'Several cities in one week', A4: 'Same-day distant reviews',
  A5: 'Short texts', A6: 'Copy-paste text', A7: 'Burst participant', A8: 'Reworded template (AI)',
}

export function ReviewsTable({ report, namer, selectedGroup }: { report: Report; namer: Namer; selectedGroup: string | null }) {
  const [showUnchecked, setShowUnchecked] = useState(false)
  const members = useMemo(
    () => new Set(selectedGroup ? report.groups.find((g) => g.group_id === selectedGroup)?.members ?? [] : []),
    [report, selectedGroup],
  )
  const hidden = report.reviews.filter((r) => r.label === 'not_checked').length
  const rows = report.reviews
    .filter((r) => showUnchecked || r.label !== 'not_checked')
    .sort((a, b) => Number(b.contributor_id != null && members.has(b.contributor_id)) - Number(a.contributor_id != null && members.has(a.contributor_id)))
  return (
    <div>
      <div className="row small" style={{ marginBottom: 8 }}>
        <label className="toggle">
          <input type="checkbox" checked={showUnchecked} onChange={(e) => setShowUnchecked(e.target.checked)} />
          Show {hidden} reviews whose authors weren't checked
        </label>
        <span className="muted">"Not checked" is neutral: those reviewers' histories weren't fetched (budget).</span>
      </div>
      <div style={{ maxHeight: 520, overflow: 'auto' }}>
        <table>
          <thead><tr><th>Reviewer</th><th>Rating</th><th>Date</th><th>Label</th><th>Signals</th><th>Text</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.review_id} className={r.contributor_id && members.has(r.contributor_id) ? 'selected' : ''}>
                <td>{namer.reviewer(r.contributor_id)}{r.reviewer_reviews != null && <div className="muted small">{r.reviewer_reviews} reviews</div>}</td>
                <td className="num">{r.rating ?? '–'}★</td>
                <td className="num small">{r.day ?? '–'}</td>
                <td><span className="row" style={{ gap: 6 }}><i className={`swatch ${r.label}`} />{LABEL_TEXT[r.label]}</span></td>
                <td className="small">{r.badges.map((b) => <span key={b} className="pill" title={BADGE_NAMES[b]} style={{ marginRight: 4 }}>{BADGE_NAMES[b] ?? b}</span>)}</td>
                <td className="small" style={{ maxWidth: 380 }}>
                  {r.text
                    ? <span title={r.text}>{r.text.length > 140 ? `${r.text.slice(0, 140)}…` : r.text}</span>
                    : <span className="muted">[text not included: {r.text_length ?? 0} characters]</span>}
                  {r.cluster && <div className="muted">near-duplicate group {r.cluster}</div>}
                  {r.stock_phrase && <div className="muted">common stock phrase (not counted)</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ClientTable({ rows, namer }: { rows: ClientRow[]; namer: Namer }) {
  if (!rows.length) return <p className="muted">No shared places.</p>
  return (
    <div style={{ maxHeight: 420, overflow: 'auto' }}>
      <table>
        <thead><tr><th>Place</th><th>Area</th><th>Type</th><th>Members</th><th>When</th><th>Avg rating</th><th>Distance</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.place_key}>
              <td><strong>{namer.place(r.place_key)}</strong>{r.core && <span className="pill small" style={{ marginLeft: 6 }}>core</span>}</td>
              <td>{r.area ?? '–'}</td>
              <td className="small">{r.type ?? '–'}</td>
              <td className="small" title={r.members.map((m) => namer.reviewer(m)).join(', ')}>
                <strong className="num">{r.member_count}</strong> <span className="muted">{r.members.slice(0, 3).map((m) => namer.reviewer(m)).join(', ')}{r.members.length > 3 ? '…' : ''}</span>
              </td>
              <td className="num small">{r.date_from ? `${r.date_from} – ${r.date_to}` : 'unknown'}</td>
              <td className="num">{fmt(r.avg_rating, 1)}★</td>
              <td className="num small">{r.distance_km != null ? `${r.distance_km} km` : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
