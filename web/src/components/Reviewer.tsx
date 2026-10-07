// A reviewer's public history, drawn: the Contributor Reviews API made visible.
// Everything here reads `report.histories`; nothing is scored in the browser, only counted.

import { MapPin, Star, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { BADGE_NAMES, day, LABEL_TEXT } from '../labels'
import { EASE } from '../motion'
import type { Namer } from '../names'
import type { History, HistoryItem, Report } from '../types'
import { Stars } from './ui'

/* ---------- shared scales ---------- */

/** Star gold means rating: 1★ is the empty-star grey, 5★ full gold. */
export const starFill = (r: number | null) =>
  r == null ? 'var(--label-unchecked)' : `color-mix(in srgb, var(--gold) ${Math.round(((r - 1) / 4) * 100)}%, var(--star-empty))`

const KM_MAX = 3000
/** 0 at the business, 1 at 3000 km, log scale so the neighbourhood and the far side of India both read. */
export const kmScale = (km: number | null) => (km == null ? null : Math.min(1, Math.log10(1 + Math.max(0, km)) / Math.log10(1 + KM_MAX)))

/** Google's profile count can lag what the API returns; never show fewer reviews than are on screen. */
export const reviewCount = (h: History) => Math.max(h.total_reviews ?? 0, h.visible)

export function areasOf(h: History) {
  const counts = new Map<string, number>()
  h.items.forEach((it) => it.area && counts.set(it.area, (counts.get(it.area) ?? 0) + 1))
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
}

const dayNum = (d: string) => Date.parse(`${d.slice(0, 10)}T00:00:00Z`) / 86_400_000

/* ---------- context: any view can open a reviewer ---------- */

const Ctx = createContext<{ open: (cid: string) => void }>({ open: () => {} })
export const useReviewer = () => useContext(Ctx)

export function ReviewerProvider({ report, namer, children }: { report: Report; namer: Namer; children: ReactNode }) {
  const [cid, setCid] = useState<string | null>(null)
  const open = useCallback((id: string) => setCid(id), [])
  useEffect(() => {
    if (!cid) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setCid(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cid])
  return (
    <Ctx.Provider value={{ open }}>
      {children}
      <AnimatePresence>
        {cid && (
          <>
            <motion.div key="scrim" className="scrim" onClick={() => setCid(null)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.aside key="drawer" className="drawer" role="dialog" aria-modal="true" aria-label={`Reviewer ${namer.reviewer(cid)}`}
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ duration: 0.45, ease: EASE }}>
              <button className="icon-btn drawer-close" onClick={() => setCid(null)} aria-label="Close"><X size={16} /></button>
              <Dossier report={report} namer={namer} cid={cid} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </Ctx.Provider>
  )
}

/* ---------- the profile ---------- */

function Dossier({ report, namer, cid }: { report: Report; namer: Namer; cid: string }) {
  const row = report.reviewers.find((r) => r.contributor_id === cid)
  const here = report.reviews.filter((r) => r.contributor_id === cid)
  const h = report.histories?.[cid]
  const label = row?.label ?? here[0]?.label ?? 'not_checked'
  const areas = h ? areasOf(h) : []
  const rated = h?.items.filter((i) => i.rating != null) ?? []
  const five = rated.filter((i) => i.rating === 5).length
  const types = useMemo(() => {
    const m = new Map<string, number>()
    h?.items.filter((i) => !i.this).forEach((i) => m.set(i.type_group, (m.get(i.type_group) ?? 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6)
  }, [h])
  const others = h ? h.items.filter((i) => !i.this).length : 0

  return (
    <div className="dossier">
      <div className="row small secondary" style={{ gap: 8 }}>
        <i className={`swatch ${label}`} /> {LABEL_TEXT[label]}
        {row && <span className="muted">· {row.reason === 'baseline' ? 'picked at random as a baseline' : `opened in round ${row.round} (high priority)`}</span>}
      </div>
      <h2 className="dossier-name">{namer.reviewer(cid)}</h2>

      {here.map((r) => (
        <div key={r.review_id} className="here-line">
          <Star size={15} style={{ color: 'var(--gold)' }} fill="var(--gold)" />
          <span>Reviewed this business</span><Stars rating={r.rating} /><span className="muted num">{day(r.day)}</span>
        </div>
      ))}

      {!h ? (
        <div className="notice" style={{ marginTop: 26 }}>
          {row && row.status !== 'ok'
            ? `This profile's history was ${row.status === 'private' ? 'private' : 'empty or unavailable'}, so there is nothing to compare.`
            : `This reviewer's history wasn't fetched (only the most unusual reviewers are opened). ${here[0]?.reviewer_reviews != null ? `Google lists ${here[0].reviewer_reviews} review${here[0].reviewer_reviews === 1 ? '' : 's'} on the profile.` : ''}`}
        </div>
      ) : (
        <>
          <div className="dossier-stats">
            <Stat v={reviewCount(h)} l="reviews on Google" />
            <Stat v={areas.length} l={areas.length === 1 ? 'city' : 'cities'} />
            <Stat v={rated.length ? `${Math.round((five / rated.length) * 100)}%` : '–'} l="of them 5★" />
            <Stat v={h.home_area ?? '–'} l="home area" small />
          </div>

          {others === 0 ? (
            <div className="lonely">
              <svg width="120" height="120" viewBox="-60 -60 120 120" aria-hidden>
                {[20, 38, 56].map((r) => <circle key={r} r={r} fill="none" stroke="var(--rule)" strokeDasharray="2 4" />)}
                <motion.path d={STAR} fill="var(--gold)" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 260, damping: 14, delay: 0.3 }} />
              </svg>
              <div>
                <strong>Its whole public history is this one review.</strong>
                <p className="secondary small" style={{ marginTop: 6 }}>No other place, no other city, no other date. A real customer can look like this too; what matters is how many such accounts arrive together.</p>
              </div>
            </div>
          ) : (
            <>
              <h3 className="dossier-h">Where they review, around this business</h3>
              <Radar report={report} items={h.items} />
              <h3 className="dossier-h">When, and how far away</h3>
              <LifeLine items={h.items} />
            </>
          )}

          {areas.length > 0 && (
            <>
              <h3 className="dossier-h">Cities</h3>
              <div className="row wrap" style={{ gap: 6 }}>
                {areas.slice(0, 12).map(([a, n]) => <span key={a} className="chip"><MapPin size={12} />{a} <span className="num muted">{n}</span></span>)}
              </div>
            </>
          )}
          {types.length > 0 && (
            <>
              <h3 className="dossier-h">What kinds of places</h3>
              <div className="col" style={{ gap: 6 }}>
                {types.map(([t, n], i) => (
                  <div key={t} className="type-row">
                    <span className="secondary small">{t}</span>
                    <div className="bar-track" style={{ height: 8 }}>
                      <motion.div className="bar-fill" style={{ background: 'var(--ink-2)' }} initial={{ width: 0 }} animate={{ width: `${(n / types[0][1]) * 100}%` }} transition={{ duration: 0.7, ease: EASE, delay: 0.2 + i * 0.05 }} />
                    </div>
                    <span className="num small muted">{n}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          <p className="muted tiny" style={{ marginTop: 18 }}>
            {h.visible} of {reviewCount(h)} reviews visible{reviewCount(h) > h.visible ? ' (the rest are older than the API returns)' : ''}. Dates are approximate (Google shows "3 months ago").
          </p>
        </>
      )}

      {row && row.badges.length > 0 && (
        <>
          <h3 className="dossier-h">Signals on this account</h3>
          <div className="row wrap" style={{ gap: 6 }}>{row.badges.map((b) => <span key={b.code} className="badge">{BADGE_NAMES[b.code] ?? b.name}</span>)}</div>
        </>
      )}
    </div>
  )
}

function Stat({ v, l, small }: { v: ReactNode; l: string; small?: boolean }) {
  return (
    <div>
      <div className={`fig ${small ? 'stat-sm' : 'stat-v'}`}>{v}</div>
      <div className="muted small">{l}</div>
    </div>
  )
}

const STAR = 'M0 -11 L3.2 -3.6 L11 -3.4 L5 1.8 L6.9 9.6 L0 5.3 L-6.9 9.6 L-5 1.8 L-11 -3.4 L-3.2 -3.6 Z'

/* ---------- radar: the business at the centre, each place at its bearing and (log) distance ---------- */

function bearing(lat1: number, lng1: number, lat2: number, lng2: number) {
  const r = Math.PI / 180
  const y = Math.sin((lng2 - lng1) * r) * Math.cos(lat2 * r)
  const x = Math.cos(lat1 * r) * Math.sin(lat2 * r) - Math.sin(lat1 * r) * Math.cos(lat2 * r) * Math.cos((lng2 - lng1) * r)
  return Math.atan2(y, x)
}

export function Radar({ report, items, size = 340 }: { report: Report; items: HistoryItem[]; size?: number }) {
  const { lat, lng } = report.place
  const R = size / 2 - 22
  const pts = items.filter((i) => !i.this && i.km != null && i.lat != null && i.lng != null)
  if (lat == null || lng == null || !pts.length) return <p className="muted small">No coordinates to place these reviews.</p>
  const rings = [10, 100, 1000]
  // Same-place reviews overlap; a small golden-angle spread keeps them countable.
  const seen = new Map<string, number>()
  const labelled = new Set<string>()
  const placed: { x: number; y: number }[] = []
  return (
    <svg width="100%" viewBox={`${-size / 2} ${-size / 2} ${size} ${size}`} style={{ maxWidth: size, display: 'block' }} role="img"
      aria-label={`${pts.length} reviewed places by distance and direction from this business`}>
      {rings.map((km) => (
        <g key={km}>
          <circle r={kmScale(km)! * R} fill="none" stroke="var(--rule)" strokeDasharray="2 4" />
          <text x={4} y={-kmScale(km)! * R - 3} fontSize="9.5" fill="var(--muted)">{km >= 1000 ? `${km / 1000}k` : km} km</text>
        </g>
      ))}
      <circle r={R} fill="none" stroke="var(--rule)" />
      {pts.map((p, i) => {
        const key = `${p.lat},${p.lng}`
        const k = seen.get(key) ?? 0
        seen.set(key, k + 1)
        const a = bearing(lat, lng, p.lat!, p.lng!) + k * 2.399
        const rr = kmScale(p.km)! * R + (k ? 3 + k : 0)
        const x = Math.sin(a) * rr
        const y = -Math.cos(a) * rr
        const showLabel = !!p.area && p.km! > 150 && !labelled.has(p.area) && labelled.size < 6 && placed.every((q) => Math.abs(q.x - x) > 70 || Math.abs(q.y - y) > 14)
        if (showLabel) {
          labelled.add(p.area!)
          placed.push({ x, y })
        }
        return (
          <g key={i}>
            <motion.circle cx={x} cy={y} r={4.2} fill={starFill(p.rating)} stroke="var(--surface)" strokeWidth={1}
              initial={{ opacity: 0, scale: 0 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.25 + Math.min(1.2, i * 0.012), type: 'spring', stiffness: 300, damping: 18 }}>
              <title>{`${p.area ?? 'Unknown area'}, ${Math.round(p.km!)} km, ${p.rating ?? '?'}★, ${day(p.day)}`}</title>
            </motion.circle>
            {showLabel && <text x={x + 7} y={y + 3} fontSize="10" fill="var(--ink-2)">{p.area}</text>}
          </g>
        )
      })}
      <path d={STAR} fill="var(--gold)" stroke="var(--surface)" strokeWidth={1.5} />
    </svg>
  )
}

/* ---------- life line: time across, distance up ---------- */

export function LifeLine({ items, height = 150 }: { items: HistoryItem[]; height?: number }) {
  const dated = items.filter((i) => i.day)
  if (dated.length < 2) return null
  const days = dated.map((i) => dayNum(i.day!))
  const lo = Math.min(...days)
  const hi = Math.max(lo + 180, Math.max(...days))
  const W = 480
  const pad = { l: 44, r: 10, t: 10, b: 22 }
  const x = (d: number) => pad.l + ((d - lo) / (hi - lo)) * (W - pad.l - pad.r)
  const y = (km: number | null) => pad.t + (1 - (kmScale(km) ?? 0)) * (height - pad.t - pad.b)
  const years: number[] = []
  for (let yr = new Date(lo * 86_400_000).getUTCFullYear() + 1; yr <= new Date(hi * 86_400_000).getUTCFullYear(); yr++) years.push(yr)
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${height}`} role="img" aria-label="Reviews over time by distance from this business">
      {[0, 10, 100, 1000].map((km) => (
        <g key={km}>
          <line x1={pad.l} x2={W - pad.r} y1={y(km)} y2={y(km)} stroke="var(--rule-soft)" />
          <text x={pad.l - 6} y={y(km) + 3} fontSize="9.5" textAnchor="end" fill="var(--muted)">{km === 0 ? 'here' : `${km} km`}</text>
        </g>
      ))}
      {years.map((yr) => {
        const xx = x(Date.UTC(yr, 0, 1) / 86_400_000)
        return <g key={yr}><line x1={xx} x2={xx} y1={pad.t} y2={height - pad.b} stroke="var(--rule-soft)" /><text x={xx} y={height - 6} fontSize="9.5" textAnchor="middle" fill="var(--muted)">{yr}</text></g>
      })}
      {dated.map((it, i) => it.this ? (
        <path key={i} d={STAR} transform={`translate(${x(dayNum(it.day!))},${y(0)}) scale(0.75)`} fill="var(--gold)" stroke="var(--surface)" />
      ) : (
        <motion.circle key={i} cx={x(dayNum(it.day!))} cy={y(it.km)} r={3.6} fill={starFill(it.rating)} stroke="var(--surface)" strokeWidth={0.8}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 + Math.min(1, i * 0.01) }}>
          <title>{`${it.area ?? 'Unknown area'}, ${it.km != null ? `${Math.round(it.km)} km, ` : ''}${it.rating ?? '?'}★, ${day(it.day)}`}</title>
        </motion.circle>
      ))}
    </svg>
  )
}

/* ---------- mini strip, for grids and the live view ---------- */

/** A reviewer's history in one line: each review a dot by age (older left), raised by distance when known. */
export function HistoryStrip({ points, width = 220, height = 40, animate = true }: {
  points: { age: number; km?: number | null; rating: number | null; here?: boolean }[]; width?: number; height?: number; animate?: boolean
}) {
  const maxAge = Math.max(365, ...points.map((p) => p.age))
  const x = (age: number) => 6 + (1 - age / maxAge) * (width - 12)
  const y = (p: { km?: number | null }) => (p.km === undefined ? height / 2 : height - 6 - (kmScale(p.km ?? 0) ?? 0) * (height - 12))
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" aria-hidden style={{ display: 'block', overflow: 'visible', maxWidth: width }}>
      <line x1={4} x2={width - 4} y1={height - 6} y2={height - 6} stroke="var(--rule)" />
      {points.map((p, i) => p.here ? (
        <path key={i} d={STAR} transform={`translate(${x(p.age)},${height - 6}) scale(0.55)`} fill="var(--gold)" />
      ) : (
        <motion.circle key={i} cx={x(p.age)} cy={y(p)} r={2.6} fill={starFill(p.rating)}
          initial={animate ? { opacity: 0, cy: height - 6 } : false} animate={{ opacity: 1, cy: y(p) }}
          transition={{ delay: Math.min(0.8, i * 0.008), duration: 0.5, ease: EASE }} />
      ))}
    </svg>
  )
}

/** Strip points from a report history: ages measured back from its newest review. */
export function stripPoints(h: History, newest: number) {
  return h.items.filter((i) => i.day).map((i) => ({ age: Math.max(0, newest - dayNum(i.day!)), km: i.km, rating: i.rating, here: i.this }))
}

export function newestDay(report: Report) {
  return report.sample.last ? dayNum(report.sample.last) : Date.now() / 86_400_000
}

/* ---------- every reviewer opened, as a grid of strips ---------- */

export function CheckedGrid({ report, namer }: { report: Report; namer: Namer }) {
  const { open } = useReviewer()
  const newest = newestDay(report)
  const linked = new Set(report.graph.edges.flatMap((e) => [e.source, e.target]))
  const rows = report.reviewers
  if (!rows.length) return null
  return (
    <div className="checked-grid">
      {rows.map((r, i) => {
        const h = report.histories?.[r.contributor_id]
        const n = h?.items.filter((x) => !x.this).length ?? 0
        const areas = h ? areasOf(h).length : 0
        return (
          <motion.button key={r.contributor_id} className={`hcard ${linked.has(r.contributor_id) ? 'linked' : ''} ${r.reason === 'baseline' ? 'baseline' : ''}`}
            onClick={() => open(r.contributor_id)} initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: Math.min(0.6, i * 0.03), ease: EASE }}>
            <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
              <strong className="hcard-name">{namer.reviewer(r.contributor_id)}</strong>
              <i className={`swatch ${r.label}`} title={LABEL_TEXT[r.label]} />
            </div>
            <div style={{ margin: '10px 0 8px' }}>
              {h ? <HistoryStrip points={stripPoints(h, newest)} width={200} height={36} /> : <div className="muted tiny" style={{ height: 36, display: 'grid', alignItems: 'center' }}>history {r.status === 'ok' ? 'unavailable' : r.status}</div>}
            </div>
            <div className="muted tiny">
              {h ? (n === 0 ? 'Only this review' : `${reviewCount(h).toLocaleString('en-IN')} reviews · ${areas} ${areas === 1 ? 'city' : 'cities'}`) : '–'}
              {r.reason === 'baseline' && ' · random baseline'}
            </div>
          </motion.button>
        )
      })}
    </div>
  )
}
