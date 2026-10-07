// The sieve: the newest reviews flow left to right as dots. Each review leaves the trunk at the first warning sign
// the reader has set aside and drops into that sign's branch; the rest reach "Kept". Setting a sign aside or keeping
// it moves exactly its reviews, so the reader sees what changed. Nothing here re-scores a review: the signs come
// from the report, the reader only chooses which ones to set aside.

import { motion, useReducedMotion } from 'motion/react'
import { useCallback, useMemo, useState } from 'react'
import { day, fmt } from '../labels'
import { useWidth } from '../motion'
import type { Report, ReviewRow, SieveSign, SignKey } from '../types'
import { starFill } from './Reviewer'

export type Branch = SignKey | 'kept'

const mean = (rows: ReviewRow[]) => {
  const v = rows.map((r) => r.rating).filter((x): x is number => x != null)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

/** The reader's choice of signs to set aside, and where each review lands because of it. */
export function useSieve(report: Report) {
  const sieve = report.sieve
  const [aside, setAside] = useState<Set<SignKey>>(() => new Set(sieve?.set_aside_by_default ?? []))
  const toggle = useCallback((k: SignKey) => setAside((prev) => {
    const next = new Set(prev)
    if (next.has(k)) next.delete(k)
    else next.add(k)
    return next
  }), [])
  const reset = useCallback(() => setAside(new Set(sieve?.set_aside_by_default ?? [])), [sieve])
  const order = useMemo(() => sieve?.order ?? [], [sieve])
  const branchOf = useCallback((r: ReviewRow): Branch => (r.signs ?? []).find((s) => aside.has(s)) ?? 'kept', [aside])
  const groups = useMemo(() => {
    const g = { kept: [] as ReviewRow[] } as Record<Branch, ReviewRow[]>
    order.forEach((k) => (g[k] = []))
    report.reviews.forEach((r) => g[branchOf(r)].push(r))
    return g
  }, [report, order, branchOf])
  const isDefault = useMemo(() => {
    const d = new Set(sieve?.set_aside_by_default ?? [])
    return d.size === aside.size && [...d].every((k) => aside.has(k))
  }, [aside, sieve])
  return { sieve, order, aside, toggle, reset, isDefault, branchOf, groups, keptMean: mean(groups.kept), keptCount: groups.kept.length }
}
export type SieveState = ReturnType<typeof useSieve>

export function signTone(k: SignKey, s: SieveSign | undefined): string {
  if (k === 'linked_group') return 'var(--label-ring)'
  if (s?.strength === 'context') return 'var(--label-none)'
  return 'var(--label-suspicious)'
}

/* ---------- geometry ----------
   Vertical: the newest reviews sit in a card at the top, a trunk runs down the left edge, each sign is a row the
   trunk branches into, and what's left reaches "Kept" at the bottom. Rows have room for a name, an explanation and
   the sign's own dots, however many signs there are. */

const P = 8 // dot pitch
const R = 3 // dot radius
const TX = 30 // trunk's left edge
const T = 46 // trunk width for every review
const LEAF_X = TX + T + 64
const SRC_H = 88
const SINK_H = 118
const ROW_H = 96
const ROW_GAP = 14
const GAP = 34 // between the source card, the rows and the sink card
const PAD = 16
const DOT_COLS = 34

interface Grid { x: number; y: number; cols: number }
const at = (g: Grid, j: number) => ({ x: g.x + (j % g.cols) * P + P / 2, y: g.y + Math.floor(j / g.cols) * P + P / 2 })
const rowsFor = (n: number, cols: number) => Math.max(1, Math.ceil(n / cols))

function useLayout(width: number, report: Report, gates: SignKey[]) {
  return useMemo(() => {
    const n = report.reviews.length
    const W = Math.max(width, 720)
    const wideCols = Math.min(60, Math.floor((W * 0.46) / P))
    const nodeDotsH = rowsFor(n, wideCols) * P
    const srcH = Math.max(SRC_H, nodeDotsH + 2 * PAD + 4)
    const sinkH = Math.max(SINK_H, nodeDotsH + 2 * PAD + 4)
    const srcBottom = srcH
    const rowTop = (i: number) => srcBottom + GAP + i * (ROW_H + ROW_GAP)
    const rowMid = Object.fromEntries(gates.map((k, i) => [k, rowTop(i) + ROW_H / 2])) as Record<SignKey, number>
    const rowsEnd = gates.length ? rowTop(gates.length - 1) + ROW_H : srcBottom
    const sinkTop = rowsEnd + GAP
    const height = sinkTop + sinkH
    const nodeGrid = (top: number, h: number): Grid => ({ x: W - PAD - wideCols * P, y: top + (h - nodeDotsH) / 2, cols: wideCols })
    const leafCols = Math.min(DOT_COLS, Math.floor((W - LEAF_X) * 0.36 / P))
    const leaves = Object.fromEntries(gates.map((k) => {
      const rows = rowsFor(report.sieve?.signs[k]?.count ?? 1, leafCols)
      return [k, { x: W - PAD - leafCols * P, y: rowMid[k] - (rows * P) / 2, cols: leafCols }]
    })) as Record<SignKey, Grid>
    return { W, n, srcH, sinkH, srcBottom, sinkTop, rowMid, rowTop, leaves, leafCols, height, src: nodeGrid(0, srcH), sink: nodeGrid(sinkTop, sinkH) }
  }, [width, report, gates])
}
type Layout = ReturnType<typeof useLayout>

/** Trunk width before each sign's row, and each branch's width, for the current choice. */
function flows(layout: Layout, gates: SignKey[], counts: Record<Branch, number>) {
  const total = Math.max(1, layout.n)
  const th = (c: number) => (c > 0 ? Math.max(3, (c / total) * T) : 0)
  let left = layout.n
  const before: Record<string, number> = {}
  const branch: Record<string, number> = {}
  for (const k of gates) {
    before[k] = th(left)
    branch[k] = counts[k] > 0 ? Math.max(2.5, (counts[k] / total) * T) : 0
    left -= counts[k]
  }
  return { before, branch, end: th(left) }
}

/** The trunk: a straight left edge, and a right edge that steps in where each branch leaves. */
function trunkPath(layout: Layout, gates: SignKey[], f: ReturnType<typeof flows>) {
  const top = layout.srcBottom
  const bottom = layout.sinkTop
  const startW = gates.length ? f.before[gates[0]] : f.end
  let d = `M ${TX} ${top} L ${TX + startW} ${top}`
  gates.forEach((k, i) => {
    const y = layout.rowMid[k]
    const after = i === gates.length - 1 ? f.end : f.before[gates[i + 1]]
    d += ` L ${TX + f.before[k]} ${y - 38} C ${TX + f.before[k]} ${y - 18} ${TX + after} ${y - 14} ${TX + after} ${y + 6}`
  })
  d += ` L ${TX + f.end} ${bottom} L ${TX} ${bottom} Z`
  return d
}

/* ---------- the graph ---------- */

export function SieveGraph({ report, state, selected, onSelect }: {
  report: Report; state: SieveState; selected: Branch; onSelect: (b: Branch) => void
}) {
  const sieve = report.sieve!
  const gates = useMemo(() => sieve.order.filter((k) => sieve.signs[k].count > 0), [sieve])
  const [ref, width] = useWidth<HTMLDivElement>()
  const layout = useLayout(width, report, gates)
  const counts = useMemo(() => Object.fromEntries((['kept', ...sieve.order] as Branch[]).map((b) => [b, state.groups[b]?.length ?? 0])) as Record<Branch, number>, [state.groups, sieve])
  const f = flows(layout, gates, counts)
  const ready = width > 0

  return (
    <div ref={ref} className="sieve" style={{ height: layout.height }}>
      {ready && (
        <>
          <svg className="sieve-svg" width={layout.W} height={layout.height} aria-hidden>
            <path d={trunkPath(layout, gates, f)} className="sieve-trunk" />
            {gates.map((k) => {
              const y = layout.rowMid[k]
              const w = f.branch[k]
              const on = state.aside.has(k)
              const x0 = TX + f.before[k] - Math.max(w, 2) / 2
              const d = `M ${x0} ${y - 40} C ${x0} ${y - 12} ${x0 + 14} ${y} ${x0 + 40} ${y} L ${LEAF_X} ${y}`
              const tone = signTone(k, sieve.signs[k])
              return on && w > 0
                ? <path key={k} d={d} fill="none" stroke={tone} strokeOpacity={sieve.signs[k].strength === 'opinion' ? 0.22 : 0.3} strokeWidth={w} />
                : <path key={k} d={`M ${TX + f.before[k] + 6} ${y} L ${LEAF_X} ${y}`} fill="none" stroke="var(--line-strong)" strokeDasharray="2 5" strokeWidth={1.4} />
            })}
          </svg>

          <div className="sieve-node sieve-src" style={{ left: 0, right: 0, height: layout.srcH }}>
            <div className="sieve-node-label">The newest {layout.n} reviews</div>
            <div className="sieve-avg"><span className="fig">{fmt(sieve.all.mean, 2)}</span><span className="star">★</span><span className="muted small">&nbsp;average</span></div>
          </div>

          {gates.map((k) => (
            <Leaf key={k} k={k} sign={sieve.signs[k]} layout={layout} on={state.aside.has(k)} count={counts[k]} rows={state.groups[k] ?? []}
              selected={selected === k} onToggle={() => state.toggle(k)} onSelect={() => onSelect(k)} />
          ))}

          <button type="button" className={`sieve-node sieve-sink ${selected === 'kept' ? 'selected' : ''}`} style={{ left: 0, right: 0, top: layout.sinkTop, height: layout.sinkH }} onClick={() => onSelect('kept')}>
            <div className="sieve-node-label">Kept</div>
            <div className="sieve-avg big"><span className="fig">{fmt(state.keptMean, 2)}</span><span className="star">★</span></div>
            <div className="muted small"><span className="num">{state.keptCount}</span> of {layout.n} reviews</div>
          </button>

          <Dots report={report} layout={layout} state={state} f={f} />
        </>
      )}
    </div>
  )
}

function Leaf({ k, sign, layout, on, count, rows, selected, onToggle, onSelect }: {
  k: SignKey; sign: SieveSign; layout: Layout; on: boolean; count: number; rows: ReviewRow[]; selected: boolean; onToggle: () => void; onSelect: () => void
}) {
  const tone = signTone(k, sign)
  const m = mean(rows)
  const dotsW = layout.leafCols * P + PAD
  return (
    <div className={`sieve-node sieve-leaf ${on ? 'on' : 'off'} ${sign.strength} ${selected ? 'selected' : ''}`}
      style={{ left: LEAF_X, right: 0, top: layout.rowMid[k] - ROW_H / 2, height: ROW_H, paddingRight: dotsW + 12, ['--tone' as string]: tone }}>
      <button type="button" className="leaf-hit" onClick={onSelect} aria-label={`Show the reviews: ${sign.name}`} />
      <span className="fig leaf-count">{on ? count : sign.count}</span>
      <div className="leaf-body">
        <div className="leaf-name">{sign.name}</div>
        <div className="leaf-explain">{sign.explain}</div>
        <div className="tiny muted">
          {on
            ? <>{count > 0 && m != null ? <>these average <span className="num">{fmt(m, 1)}</span>★</> : 'none left here'}{count !== sign.count && <> ({sign.count - count} more left at an earlier sign)</>}</>
            : <>kept: {sign.count === 1 ? "this review counts" : `these ${sign.count} reviews count`} towards Kept</>}
        </div>
      </div>
      <label className="leaf-switch" title={on ? 'Keep these reviews' : 'Set these reviews aside'}>
        <input type="checkbox" className="sr-only" checked={on} onChange={onToggle} aria-label={`Set aside: ${sign.name}`} />
        <span className={`switch-track ${on ? 'on' : ''}`}><span className="switch-thumb" /></span>
        <span className="tiny">{on ? 'Set aside' : 'Kept'}</span>
      </label>
    </div>
  )
}

/* ---------- the reviews as dots ---------- */

interface Pt { x: number; y: number }

function Dots({ report, layout, state, f }: { report: Report; layout: Layout; state: SieveState; f: ReturnType<typeof flows> }) {
  const reduce = useReducedMotion()
  const reviews = report.reviews
  // Where each review lands: its branch and its slot in that node's grid (in the reviews' own order, newest first).
  const targets = useMemo(() => {
    const slot: Record<string, number> = {}
    return reviews.map((r) => {
      const b = state.branchOf(r)
      const j = (slot[b] = (slot[b] ?? -1) + 1)
      const grid = b === 'kept' ? layout.sink : layout.leaves[b]
      return { b, pos: grid ? at(grid, j) : at(layout.sink, j) }
    })
  }, [reviews, state, layout])

  // A lane inside the trunk: reviews leaving at a sign travel in the right-hand slice that peels off there.
  const lane = useCallback((i: number, b: Branch) => {
    const k = (i * 0.618) % 1
    if (b === 'kept') return TX + 2 + k * Math.max(1, f.end - 4)
    const w = f.branch[b] ?? 3
    return TX + f.before[b] - w + 1 + k * Math.max(1, w - 2)
  }, [f])

  // The previous landing places, kept in state (not a ref) so moves can start where each dot was.
  const [snap, setSnap] = useState<{ cur: typeof targets; prev: typeof targets | null }>({ cur: targets, prev: null })
  if (snap.cur !== targets) setSnap({ cur: targets, prev: snap.cur })
  const old = snap.cur !== targets ? snap.cur : snap.prev
  const plans = useMemo(() => {
    const sinkIn = layout.sinkTop + 4
    const out = (b: SignKey, x: number): Pt[] => [{ x, y: layout.rowMid[b] - 30 }, { x: x + 30, y: layout.rowMid[b] }, { x: LEAF_X + 10, y: layout.rowMid[b] }]
    return targets.map((t, i) => {
      const x = lane(i, t.b)
      const src = at(layout.src, i)
      if (!old) {
        const pts: Pt[] = [src, { x, y: layout.srcBottom + 2 }, ...(t.b === 'kept' ? [{ x, y: sinkIn }] : out(t.b, x)), t.pos]
        return { pts, from: true, delay: 0.5 + i * 0.012 }
      }
      const o = old[i]
      if (!o || o.b === t.b) return { pts: [t.pos], from: false, delay: 0 }
      const ox = lane(i, o.b)
      const back: Pt[] = o.b === 'kept' ? [{ x: ox, y: sinkIn }] : [{ x: LEAF_X + 10, y: layout.rowMid[o.b] }, { x: ox + 30, y: layout.rowMid[o.b] }]
      const ahead: Pt[] = t.b === 'kept' ? [{ x, y: sinkIn }] : out(t.b, x)
      return { pts: [...back, ...ahead, t.pos], from: false, delay: (i % 25) * 0.01 }
    })
  }, [targets, old, layout, lane])

  return (
    <svg className="sieve-dots" width={layout.W} height={layout.height} aria-hidden>
      <g className="ghosts">
        {reviews.map((r, i) => {
          const q = at(layout.src, i)
          return <circle key={r.review_id} cx={q.x} cy={q.y} r={R - 0.6} />
        })}
        {report.sieve!.order.filter((k) => layout.leaves[k] && !state.aside.has(k)).flatMap((k) =>
          Array.from({ length: report.sieve!.signs[k].count }, (_, j) => {
            const q = at(layout.leaves[k], j)
            return <circle key={`${k}-${j}`} cx={q.x} cy={q.y} r={R - 0.6} />
          }))}
      </g>
      {reviews.map((r, i) => {
        const p = plans[i]
        const pts = p.pts
        const dist = pts.slice(1).reduce((acc, q, j) => acc + Math.hypot(q.x - pts[j].x, q.y - pts[j].y), 0)
        let run = 0
        const times = pts.length > 1 ? pts.map((q, j) => (j === 0 ? 0 : (run += Math.hypot(q.x - pts[j - 1].x, q.y - pts[j - 1].y)) / Math.max(1, dist))) : undefined
        const cx = p.from ? pts.map((q) => q.x) : [null, ...pts.map((q) => q.x)]
        const cy = p.from ? pts.map((q) => q.y) : [null, ...pts.map((q) => q.y)]
        const t2 = times && !p.from ? [0, ...times.map((x) => 0.05 + x * 0.95)] : times
        const duration = reduce ? 0 : p.from ? 2.1 : pts.length > 1 ? 1.2 : 0.45
        const start = pts[0]
        return (
          <motion.circle key={r.review_id} r={R} fill={starFill(r.rating)}
            initial={{ cx: start.x, cy: start.y }}
            animate={{ cx: pts.length > 1 || !p.from ? cx : start.x, cy: pts.length > 1 || !p.from ? cy : start.y } as never}
            transition={{ duration, delay: reduce ? 0 : p.delay, times: pts.length > 1 ? t2 : undefined, ease: 'easeInOut' }}>
            <title>{`${r.rating ?? '?'}★ ${day(r.day)}${r.signs?.length ? `: ${r.signs.map((s) => report.sieve!.signs[s].short).join(', ')}` : ''}`}</title>
          </motion.circle>
        )
      })}
    </svg>
  )
}
