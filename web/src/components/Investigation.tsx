// The investigation, shown as it happens: the newest reviews land on a timeline, the most unusual reviewers are
// picked, their histories open one by one, and any links between them are drawn. Fed by the live progress events,
// which carry counts, stars and day offsets only, never names. A finished check is told by CaseStory instead.

import { Link2, Shuffle } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { EASE, useWidth } from '../motion'
import type { ProgressEvent } from '../types'
import { HistoryStrip, starFill } from './Reviewer'

/* ---------- model ---------- */

interface InvReview { rating: number | null; age: number | null; n: number | null }
interface InvHistory { status: string; total: number | null; visible: number; areas: number; points: [number, number | null][] }
interface Pick { index: number; reason: string; round: number }

export interface InvState {
  reviews: InvReview[]
  shown: number | null
  total: number | null
  picks: Pick[]
  histories: Record<number, InvHistory>
  links: [number, number][]
  earlyStop: boolean
  finished: boolean
}

const EMPTY: InvState = { reviews: [], shown: null, total: null, picks: [], histories: {}, links: [], earlyStop: false, finished: false }

export function reduce(s: InvState, e: ProgressEvent): InvState {
  const d = e.data ?? {}
  switch (e.type) {
    case 'reviews_loaded':
      return {
        ...s,
        shown: (d.rating as number | null) ?? null,
        total: (d.total as number | null) ?? null,
        reviews: ((d.reviews as [number | null, number | null, number | null][]) ?? []).map(([rating, age, n]) => ({ rating, age, n })),
      }
    case 'picks': {
      const known = new Set(s.picks.map((p) => p.index))
      const add = ((d.picks as [number, string, number][]) ?? []).filter(([i]) => !known.has(i)).map(([index, reason, round]) => ({ index, reason, round }))
      return { ...s, picks: [...s.picks, ...add] }
    }
    case 'history':
      return {
        ...s,
        histories: {
          ...s.histories,
          [d.index as number]: {
            status: String(d.status ?? 'ok'),
            total: (d.total as number | null) ?? null,
            visible: Number(d.visible ?? 0),
            areas: Number(d.areas ?? 0),
            points: (d.points as [number, number | null][]) ?? [],
          },
        },
      }
    case 'links':
      return { ...s, links: (d.pairs as [number, number][]) ?? [] }
    case 'early_stop':
      return { ...s, earlyStop: true }
    case 'done':
      return { ...s, finished: true }
    default:
      return s
  }
}

/** How long to dwell after each event, so a cached (instant) run still reads as an investigation. */
function dwell(type: string): number {
  return ({ reviews_loaded: 1500, picks: 1300, history: 240, links: 1400, early_stop: 900, building_graph: 500, expanding: 60, scoring: 500 } as Record<string, number>)[type] ?? 300
}

/**
 * Plays events in order with a minimum pace. `events` may keep growing (live); the player waits for more.
 * Returns the state so far, the events already played, and whether everything received has been shown.
 */
export function usePlayback(events: ProgressEvent[], speed = 1) {
  const [cursor, setCursor] = useState(0)
  useEffect(() => {
    if (cursor >= events.length) return
    const prev = cursor > 0 ? events[cursor - 1].type : null
    const t = window.setTimeout(() => setCursor((c) => c + 1), prev ? dwell(prev) / speed : 0)
    return () => clearTimeout(t)
  }, [cursor, events, speed])
  const played = useMemo(() => events.slice(0, cursor), [events, cursor])
  const state = useMemo(() => played.reduce(reduce, EMPTY), [played])
  return { state, played, caughtUp: cursor >= events.length, restart: () => setCursor(0) }
}

/* ---------- view ---------- */

export function Investigation({ state }: { state: InvState }) {
  const pickOf = useMemo(() => new Map(state.picks.map((p, k) => [p.index, k])), [state.picks])
  const linkedIdx = useMemo(() => new Set(state.links.flat()), [state.links])
  const opened = Object.keys(state.histories).length
  const [hover, setHover] = useState<number | null>(null)

  return (
    <div className="inv">
      <section>
        <div className="inv-head">
          <h3>{state.reviews.length ? <>The newest <span className="num">{state.reviews.length}</span> reviews</> : 'Fetching the newest reviews…'}</h3>
          {state.shown != null && <span className="muted small">listing shows <b className="num" style={{ color: 'var(--ink)' }}>{state.shown}★</b>{state.total ? ` from ${state.total.toLocaleString('en-IN')}` : ''}</span>}
        </div>
        <ReviewField state={state} pickOf={pickOf} linked={linkedIdx} hover={hover} />
        <div className="legend" style={{ marginTop: 10 }}>
          <span><i className="swatch" style={{ background: 'var(--gold)' }} /> 5★ … <i className="swatch" style={{ background: 'var(--star-empty)' }} /> 1★</span>
          <span><i className="swatch" style={{ border: '1.5px solid var(--ink-2)', background: 'var(--surface)' }} /> account with one review</span>
          <span><i className="swatch" style={{ boxShadow: '0 0 0 2px var(--ink)', background: 'var(--surface)' }} /> picked to open</span>
          <span className="muted">Each column is a stretch of days, oldest left.</span>
        </div>
      </section>

      <AnimatePresence>
        {state.picks.length > 0 && (
          <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ease: EASE }} style={{ marginTop: 34 }}>
            <div className="inv-head">
              <h3>Reviewer histories opened: <span className="num">{opened}</span> of <span className="num">{state.picks.length}</span></h3>
              <span className="muted small">
                {state.picks.filter((p) => p.reason === 'priority').length} most unusual, {state.picks.filter((p) => p.reason === 'baseline').length} at random as a baseline. Each line is a reviewer's whole public history, oldest left.
              </span>
            </div>
            <Cards state={state} linked={linkedIdx} onHover={setHover} />
          </motion.section>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {state.finished && (
          <motion.div className={`inv-result ${state.links.length ? 'found' : ''}`} initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ ease: EASE }}>
            <Link2 size={18} />
            {state.links.length
              ? <span><b className="num">{state.links.length}</b> pair{state.links.length === 1 ? '' : 's'} of reviewers reviewed the same unrelated, distant places.</span>
              : <span>None of the <b className="num">{opened}</b> reviewers opened share other places.{state.earlyStop ? ' So no more were opened.' : ''}</span>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ReviewField({ state, pickOf, linked, hover }: { state: InvState; pickOf: Map<number, number>; linked: Set<number>; hover: number | null }) {
  const [box, W] = useWidth<HTMLDivElement>()
  const H = 190
  const layout = useMemo(() => {
    // A lone old review shouldn't squash the rest: the scale ends at the 95th percentile, older ones share the first column.
    const ages = state.reviews.map((r) => r.age ?? 0).sort((a, b) => a - b)
    const maxAge = Math.max(1, ages[Math.floor((ages.length - 1) * 0.95)] ?? 1)
    const bins = Math.max(12, Math.min(72, Math.floor(W / 13)))
    const per = maxAge / (bins - 1)
    const stacks = new Array(bins).fill(0)
    // Oldest left; within a column, stacked upward in arrival order.
    const slots = state.reviews.map((r) => {
      const b = bins - 1 - Math.min(bins - 1, Math.floor((r.age ?? 0) / per))
      return { b, k: stacks[b]++ }
    })
    const colW = W / bins
    const size = Math.max(4, Math.min(colW, 13, (H - 14) / Math.max(1, ...stacks)))
    return { slots, colW, size }
  }, [state.reviews, W])

  return (
    <div ref={box} className="inv-field" style={{ height: H }}>
      {W > 0 && (
        <svg width={W} height={H}>
          <line x1={0} x2={W} y1={H - 2} y2={H - 2} stroke="var(--rule)" />
          {state.reviews.map((r, i) => {
            const s = layout.slots[i]
            const x = (s.b + 0.5) * layout.colW
            const y = H - 4 - layout.size / 2 - s.k * layout.size
            const k = pickOf.get(i)
            const picked = k !== undefined
            const single = r.n != null && r.n <= 1
            const rr = layout.size / 2 - 0.8
            return (
              <g key={i}>
                <motion.circle cx={x} r={rr} initial={{ cy: -10, opacity: 0 }} animate={{ cy: y, opacity: 1 }}
                  transition={{ cy: { type: 'spring', stiffness: 240, damping: 20, delay: (i / state.reviews.length) * 0.9 }, opacity: { delay: (i / state.reviews.length) * 0.9 } }}
                  style={{ fill: single ? 'var(--surface)' : starFill(r.rating), stroke: single ? starFill(r.rating === 5 ? 5 : r.rating) : 'none', transition: 'fill .4s' }}
                  strokeWidth={single ? 1.6 : 0} />
                {picked && (
                  <motion.circle cx={x} cy={y} fill="none" initial={{ r: rr * 4, opacity: 0 }} animate={{ r: rr + 2.6, opacity: 1 }}
                    transition={{ duration: 0.6, ease: EASE, delay: Math.min(1, k * 0.07) }}
                    style={{ stroke: linked.has(i) ? 'var(--label-ring)' : 'var(--ink)', transition: 'stroke .4s' }} strokeWidth={hover === i ? 3.4 : 2} />
                )}
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

function Cards({ state, linked, onHover }: { state: InvState; linked: Set<number>; onHover: (i: number | null) => void }) {
  const wrap = useRef<HTMLDivElement>(null)
  const refs = useRef(new Map<number, HTMLDivElement>())
  const [centres, setCentres] = useState<Map<number, { x: number; y: number }>>(new Map())
  const [size, setSize] = useState({ w: 0, h: 0 })

  useLayoutEffect(() => {
    const measure = () => {
      const base = wrap.current?.getBoundingClientRect()
      if (!base) return
      const m = new Map<number, { x: number; y: number }>()
      refs.current.forEach((el, i) => {
        const r = el.getBoundingClientRect()
        m.set(i, { x: r.left - base.left + r.width / 2, y: r.top - base.top + r.height / 2 })
      })
      setCentres(m)
      setSize({ w: base.width, h: base.height })
    }
    measure()
    const t = window.setTimeout(measure, 450) // after the cards' entrance
    window.addEventListener('resize', measure)
    return () => {
      clearTimeout(t)
      window.removeEventListener('resize', measure)
    }
  }, [state.picks.length, state.links.length])

  return (
    <div ref={wrap} style={{ position: 'relative' }}>
      <div className="inv-cards">
        {state.picks.map((p, k) => {
          const h = state.histories[p.index]
          const r = state.reviews[p.index]
          const isLinked = linked.has(p.index)
          return (
            <motion.div key={p.index} ref={(el) => { if (el) refs.current.set(p.index, el); else refs.current.delete(p.index) }}
              className={`inv-card ${p.reason === 'baseline' ? 'baseline' : ''} ${isLinked ? 'linked' : ''} ${h ? 'open' : ''}`}
              onMouseEnter={() => onHover(p.index)} onMouseLeave={() => onHover(null)}
              initial={{ opacity: 0, y: 18, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ ease: EASE, duration: 0.5, delay: Math.min(0.8, (k % 10) * 0.06) }}>
              <div className="row" style={{ justifyContent: 'space-between', gap: 6 }}>
                <span className="inv-card-n num">#{k + 1}</span>
                <span className="tiny secondary">
                  {r?.rating != null && <><span style={{ color: 'var(--gold)' }}>{'★'.repeat(r.rating)}</span> here</>}
                  {p.reason === 'baseline' && <> · <Shuffle size={11} style={{ verticalAlign: -1 }} /> random</>}
                </span>
              </div>
              <div className="inv-card-strip">
                {h ? (
                  h.status === 'ok'
                    ? <HistoryStrip points={h.points.map(([age, rating]) => ({ age, rating }))} width={190} height={34} />
                    : <span className="muted tiny">profile {h.status}</span>
                ) : <div className="skeleton" style={{ height: 10, width: '100%', marginTop: 12 }} />}
              </div>
              <div className="tiny">
                {h ? (
                  h.status !== 'ok' ? <span className="muted">nothing to compare</span>
                    : h.visible <= 1 ? <b>Only this one review</b>
                    : <><b className="num">{Math.max(h.total ?? 0, h.visible).toLocaleString('en-IN')}</b> <span className="muted">reviews ·</span> <b className="num">{h.areas}</b> <span className="muted">{h.areas === 1 ? 'city' : 'cities'}</span></>
                ) : <span className="muted">{r?.n != null ? `opening a profile with ${r.n} review${r.n === 1 ? '' : 's'}…` : 'opening…'}</span>}
              </div>
            </motion.div>
          )
        })}
      </div>
      {size.w > 0 && state.links.length > 0 && (
        <svg className="inv-links" width={size.w} height={size.h}>
          {state.links.map(([a, b], i) => {
            const p = centres.get(a)
            const q = centres.get(b)
            if (!p || !q) return null
            const mx = (p.x + q.x) / 2
            const my = Math.min(p.y, q.y) - 40 - Math.abs(p.x - q.x) * 0.08
            return (
              <motion.path key={`${a}-${b}`} d={`M${p.x},${p.y} Q${mx},${my} ${q.x},${q.y}`} fill="none" stroke="var(--label-ring)" strokeWidth={2} strokeLinecap="round"
                initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 0.75 }} transition={{ duration: 0.9, ease: 'easeInOut', delay: Math.min(1.5, i * 0.05) }} />
            )
          })}
        </svg>
      )}
    </div>
  )
}
