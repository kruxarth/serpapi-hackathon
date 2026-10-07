// The rating, unpacked: every review becomes a dot stacked on its star, the pointer is their average, and the
// flagged ones are lifted out. The figures shown come from the report; the running average during the
// animation is plain arithmetic on the same ratings and lands on the report's own number.

import { RotateCcw } from 'lucide-react'
import { animate, motion, useInView, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { day } from '../labels'
import { EASE, useWidth } from '../motion'
import type { Label } from '../types'
import { starFill } from './Reviewer'

export interface UnpackDot { rating: number; day: string | null; label: Label; single: boolean }

export const FLAGGED_LABELS: Label[] = ['ring', 'possible_ring_trip', 'suspicious', 'single_use_burst']

type Phase = 'idle' | 'pour' | 'accounts' | 'aside' | 'done'

interface Props {
  dots: UnpackDot[]
  shown: number | null
  /** The report's own figures; the animation lands on them. */
  mean: number | null
  adjusted: number | null
  height?: number
  loop?: boolean
  /** Step captions under the chart. */
  steps?: boolean
  onFigure?: (v: number, phase: Phase) => void
}

const dayNum = (d: string) => Date.parse(`${d.slice(0, 10)}T00:00:00Z`) / 86_400_000

function dotFill(d: UnpackDot, phase: Phase) {
  if (phase === 'idle' || phase === 'pour') return starFill(d.rating)
  if (d.label === 'ring' || d.label === 'possible_ring_trip') return 'var(--label-ring)'
  if (d.label === 'suspicious') return 'var(--label-suspicious)'
  if (d.label === 'single_use_burst') return 'color-mix(in srgb, var(--label-suspicious) 35%, var(--surface))'
  if (d.single) return 'var(--surface)'
  return 'var(--ink-2)'
}
function dotStroke(d: UnpackDot, phase: Phase) {
  if (phase === 'idle' || phase === 'pour') return 'var(--surface)'
  if (d.label === 'single_use_burst') return 'var(--label-suspicious)'
  if (FLAGGED_LABELS.includes(d.label)) return 'var(--surface)'
  if (d.single) return 'var(--ink-2)'
  return 'var(--surface)'
}

export function RatingUnpacked({ dots, shown, mean, adjusted, height = 300, loop = false, steps = true, onFigure }: Props) {
  const [box, W] = useWidth<HTMLDivElement>()
  const seen = useRef<HTMLDivElement>(null)
  const inView = useInView(seen, { once: !loop, margin: '0px 0px -80px 0px' })
  const reduce = useReducedMotion()
  const [phase, setPhase] = useState<Phase>(reduce ? 'done' : 'idle')
  const [run, setRun] = useState(0)
  const figure = useRef<HTMLSpanElement>(null)
  const ticker = useRef<HTMLSpanElement>(null)
  const follow = useRef(onFigure)
  follow.current = onFigure

  // Arrival order is the review date, oldest first; delays mix real time (so bursts pour in together) with rank.
  const order = useMemo(() => {
    const idx = dots.map((d, i) => ({ d, i })).sort((a, b) => (a.d.day ?? '').localeCompare(b.d.day ?? ''))
    const days = idx.map(({ d }) => (d.day ? dayNum(d.day) : 0))
    // A few very old reviews shouldn't leave the chart idle: time is measured from the 5th percentile.
    const lo = days[Math.floor((days.length - 1) * 0.05)] ?? 0
    const span = Math.max(1, Math.max(...days) - lo)
    return idx.map(({ d, i }, rank) => ({ d, i, at: 0.72 * Math.max(0, (days[rank] - lo) / span) + 0.28 * (rank / Math.max(1, idx.length - 1)) }))
  }, [dots])
  const flaggedN = dots.filter((d) => FLAGGED_LABELS.includes(d.label)).length
  const singleN = dots.filter((d) => d.single).length
  const P = loop ? 2.8 : 3.4 // pour duration, seconds

  // Layout: five star columns, a tray on the right for the dots that get set aside.
  const layout = useMemo(() => {
    const axisH = 34
    const topPad = 34
    const trayW = flaggedN ? Math.min(240, W * 0.24) : 0
    const gap = flaggedN ? 28 : 0
    const plotW = Math.max(100, W - trayW - gap)
    const colW = plotW / 5
    const base = height - axisH
    const counts = [1, 2, 3, 4, 5].map((r) => dots.filter((d) => d.rating === r).length)
    const keptCounts = [1, 2, 3, 4, 5].map((r) => dots.filter((d) => d.rating === r && !FLAGGED_LABELS.includes(d.label)).length)
    const maxN = Math.max(1, ...counts)
    let size = 16
    const fits = (s: number) => {
      const per = Math.max(1, Math.floor((colW - 14) / s))
      const trayPer = trayW ? Math.max(1, Math.floor(trayW / s)) : 1
      return Math.ceil(maxN / per) * s <= base - topPad && (!trayW || Math.ceil(flaggedN / trayPer) * s <= base - topPad)
    }
    while (size > 5 && !fits(size)) size -= 0.5
    const per = Math.max(1, Math.floor((colW - 14) / size))
    const cx = (r: number) => (r - 0.5) * colW
    const slot = (r: number, k: number) => ({
      x: cx(r) - (per * size) / 2 + size / 2 + (k % per) * size,
      y: base - size / 2 - Math.floor(k / per) * size,
    })
    const trayX = plotW + gap
    const trayPer = trayW ? Math.max(1, Math.floor(trayW / size)) : 1
    const pos: { x: number; y: number }[] = []
    const kept: { x: number; y: number }[] = []
    const k1 = [0, 0, 0, 0, 0, 0]
    const k2 = [0, 0, 0, 0, 0, 0]
    let kt = 0
    for (const { d, i } of order) {
      pos[i] = slot(d.rating, k1[d.rating]++)
      if (FLAGGED_LABELS.includes(d.label)) {
        kept[i] = { x: trayX + size / 2 + (kt % trayPer) * size, y: base - size / 2 - Math.floor(kt / trayPer) * size }
        kt++
      } else kept[i] = slot(d.rating, k2[d.rating]++)
    }
    // The pointer runs on the star scale, through the column centres.
    const xOf = (v: number) => cx(Math.max(1, Math.min(5, v)))
    return { pos, kept, size, base, colW, plotW, trayX, trayW, cx, xOf, counts, keptCounts, topPad }
  }, [W, height, dots, order, flaggedN])

  // Prefix means in arrival order, so the pointer can follow the dots as they land.
  const prefix = useMemo(() => {
    const out = [shown ?? mean ?? 0]
    let s = 0
    order.forEach(({ d }, k) => {
      s += d.rating
      out.push(s / (k + 1))
    })
    return out
  }, [order, shown, mean])

  const pv = useMotionValue(shown ?? mean ?? 3)
  const px = useTransform(pv, (v) => layout.xOf(v))

  const setFig = (v: number, ph: Phase) => {
    if (figure.current) figure.current.textContent = v.toFixed(2)
    follow.current?.(v, ph)
  }

  useEffect(() => {
    if (!inView || !W) return
    if (reduce) {
      const v = flaggedN && adjusted != null ? adjusted : mean ?? 0
      pv.set(v)
      setFig(v, 'done')
      setPhase('done')
      return
    }
    let cancelled = false
    const timers: number[] = []
    const later = (s: number, fn: () => void) => timers.push(window.setTimeout(() => !cancelled && fn(), s * 1000))
    pv.set(shown ?? mean ?? 3)
    setFig(shown ?? mean ?? 0, 'idle')
    setPhase('idle')
    const lead = shown != null ? 0.9 : 0.3
    let raf = 0
    later(lead, () => {
      setPhase('pour')
      const t0 = performance.now()
      const fall = 0.45
      const tick = () => {
        const t = (performance.now() - t0) / 1000
        let n = 0
        while (n < order.length && order[n].at * P + fall <= t) n++
        // Ease from the starting figure into the running average over the first fifth of the dots, so the first
        // few reviews don't swing the pointer; from there on it is the plain average of the dots on the chart.
        const blend = Math.min(1, n / Math.max(1, order.length * 0.2))
        const v = n === order.length && mean != null ? mean : prefix[0] + (prefix[n] - prefix[0]) * blend
        pv.set(v)
        setFig(v, 'pour')
        if (ticker.current && n > 0) ticker.current.textContent = day(order[n - 1].d.day)
        if (n < order.length && !cancelled) raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
    })
    const afterPour = lead + P + 0.9
    const showAccounts = singleN > 0 || flaggedN > 0
    if (showAccounts) later(afterPour, () => setPhase('accounts'))
    const asideAt = afterPour + (showAccounts ? 1.8 : 0)
    if (flaggedN && adjusted != null) {
      later(asideAt, () => {
        setPhase('aside')
        animate(pv, adjusted, { duration: 1.4, ease: EASE, delay: 0.5, onUpdate: (v) => setFig(v, 'aside') })
      })
    }
    const doneAt = asideAt + (flaggedN ? 2.2 : 0.4)
    later(doneAt, () => setPhase('done'))
    if (loop) later(doneAt + 4, () => setRun((r) => r + 1))
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      timers.forEach(clearTimeout)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, W > 0, run, reduce])

  const aside = phase === 'aside' || (phase === 'done' && flaggedN > 0)
  const colored = phase === 'accounts' || phase === 'aside' || phase === 'done'
  const stepIdx = { idle: 0, pour: 1, accounts: 2, aside: 3, done: flaggedN ? 3 : singleN ? 2 : 1 }[phase]
  const { size } = layout
  const r = Math.max(2, size / 2 - 1.2)

  return (
    <div ref={seen} className="unpacked">
      <div className="unpack-fig">
        <span className="fig"><span ref={figure}>{(shown ?? mean ?? 0).toFixed(2)}</span><span style={{ color: 'var(--gold)' }}>★</span></span>
        <span className="unpack-cap">
          {phase === 'idle' && (shown != null ? 'what Google shows' : 'average')}
          <span style={{ display: phase === 'pour' ? 'inline' : 'none' }}>averaging the reviews as they land, up to <span ref={ticker} className="num" /></span>
          {(phase === 'accounts' || (phase === 'done' && !flaggedN)) && <>what the newest <span className="num">{dots.length}</span> reviews average</>}
          {(phase === 'aside' || (phase === 'done' && flaggedN > 0)) && <>without the <span className="num">{flaggedN}</span> flagged reviews, {adjusted != null && mean != null && adjusted > mean ? 'up' : 'down'} from <span className="num">{mean?.toFixed(2)}★</span></>}
        </span>
      </div>
      <div ref={box} style={{ position: 'relative' }}>
        {W > 0 && (
          <svg width={W} height={height} role="img"
            aria-label={`${dots.length} reviews by star rating; average ${mean ?? '?'}★${flaggedN && adjusted != null ? `, ${adjusted}★ without ${flaggedN} flagged` : ''}`}>
            {/* column floors and star labels */}
            {[1, 2, 3, 4, 5].map((s) => (
              <g key={s}>
                <line x1={layout.cx(s) - layout.colW / 2 + 8} x2={layout.cx(s) + layout.colW / 2 - 8} y1={layout.base + 1} y2={layout.base + 1} stroke="var(--rule)" strokeWidth={2} strokeLinecap="round" />
                <text x={layout.cx(s)} y={layout.base + 22} textAnchor="middle" fontSize="13" fontWeight="700" fill="var(--ink-2)">{s}<tspan fill="var(--gold)">★</tspan></text>
                <motion.text x={layout.cx(s)} textAnchor="middle" fontSize="11" fill="var(--muted)" className="num"
                  initial={false} animate={{ opacity: phase === 'idle' ? 0 : 1, y: layout.base - Math.ceil(((aside ? layout.keptCounts : layout.counts)[s - 1]) / Math.max(1, Math.floor((layout.colW - 14) / size))) * size - 8 }}
                  transition={{ duration: 0.6, ease: EASE }}>
                  {(aside ? layout.keptCounts : layout.counts)[s - 1] || ''}
                </motion.text>
              </g>
            ))}
            {layout.trayW > 0 && (
              <motion.g initial={false} animate={{ opacity: aside ? 1 : 0 }} transition={{ duration: 0.5 }}>
                <rect x={layout.trayX - 10} y={layout.topPad - 22} width={layout.trayW + 20} height={layout.base - layout.topPad + 30} rx={12}
                  fill="color-mix(in srgb, var(--label-suspicious) 6%, transparent)" stroke="var(--rule)" strokeDasharray="3 5" />
                <text x={layout.trayX + layout.trayW / 2} y={layout.base + 22} textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--ink-2)">Set aside: {flaggedN}</text>
              </motion.g>
            )}
            {/* Google's figure stays as a ghost marker so the gap stays visible */}
            {shown != null && (
              <motion.g initial={false} animate={{ opacity: phase === 'idle' ? 0 : 1 }}>
                <line x1={layout.xOf(shown)} x2={layout.xOf(shown)} y1={layout.topPad - 12} y2={layout.base} stroke="var(--gold)" strokeWidth={1.5} strokeDasharray="3 4" />
                <text x={layout.xOf(shown) + (shown > 4.6 ? -10 : 0)} y={layout.topPad - 16} textAnchor={shown > 4.6 ? 'end' : 'middle'} fontSize="11.5" fontWeight="700" fill="var(--gold)">Google {shown}★</text>
              </motion.g>
            )}
            {/* the pointer: the average of the dots on the chart */}
            <motion.g style={{ x: px }}>
              <line x1={0} x2={0} y1={layout.topPad + 4} y2={layout.base + 2} stroke="var(--ink)" strokeWidth={2} />
            </motion.g>
            <g key={run}>
              {order.map(({ d, i, at }) => {
                const p = aside ? layout.kept[i] : layout.pos[i]
                if (!p) return null
                const fl = FLAGGED_LABELS.includes(d.label)
                return (
                  <motion.circle key={i} r={r}
                    initial={reduce ? false : { cx: p.x, cy: -12, opacity: 0 }}
                    animate={{ cx: p.x, cy: phase === 'idle' ? -12 : p.y, opacity: phase === 'idle' ? 0 : 1 }}
                    // Colours are CSS variables, which motion can't interpolate: plain attributes, eased by a CSS transition.
                    fill={dotFill(d, colored ? phase : 'pour')} stroke={dotStroke(d, colored ? phase : 'pour')}
                    strokeWidth={1.4}
                    transition={phase === 'pour'
                      ? { cy: { type: 'spring', stiffness: 260, damping: 20, delay: at * P }, opacity: { duration: 0.15, delay: at * P }, default: { duration: 0.4 } }
                      : { type: 'spring', stiffness: 120, damping: 18, delay: aside && fl ? 0.02 * (i % 20) : 0 }} />
                )
              })}
            </g>
            {/* the pointer's star rides on top; its line is drawn beneath the dots */}
            <motion.g style={{ x: px }}>
              <path d="M0 -7 L2.1 -2.4 L7.2 -2.2 L3.3 1.2 L4.5 6.3 L0 3.5 L-4.5 6.3 L-3.3 1.2 L-7.2 -2.2 L-2.1 -2.4 Z"
                transform={`translate(0 ${layout.topPad - 2}) scale(1.3)`} fill="var(--gold)" stroke="var(--ink)" strokeWidth={0.8} />
            </motion.g>
          </svg>
        )}
      </div>
      {steps && (
        <ol className="unpack-steps">
          <Step on={stepIdx >= 0} active={stepIdx === 0}>{shown != null ? <>Google shows <b className="num">{shown}★</b></> : 'Start from the reviews'}</Step>
          <Step on={stepIdx >= 1} active={stepIdx === 1}>The newest <b className="num">{dots.length}</b> average <b className="num">{mean?.toFixed(2)}★</b></Step>
          {singleN > 0 && <Step on={stepIdx >= 2} active={stepIdx === 2}><b className="num">{singleN}</b> come from accounts with a single review <i className="swatch" style={{ border: '1.5px solid var(--ink-2)' }} /></Step>}
          {flaggedN > 0 && adjusted != null
            ? <Step on={stepIdx >= 3} active={stepIdx === 3}><b className="num">{flaggedN}</b> flagged set aside: <b className="num">{adjusted.toFixed(2)}★</b></Step>
            : <Step on={phase === 'done'} active={false}>No review in this sample was flagged</Step>}
          {!loop && (
            <li className="unpack-replay">
              <button className="btn ghost sm" disabled={phase !== 'done'} onClick={() => setRun((x) => x + 1)}><RotateCcw size={14} /> Replay</button>
            </li>
          )}
        </ol>
      )}
    </div>
  )
}

function Step({ on, active, children }: { on: boolean; active: boolean; children: React.ReactNode }) {
  return (
    <motion.li initial={false} animate={{ opacity: on ? 1 : 0.28 }} className={active ? 'active' : ''} transition={{ duration: 0.4 }}>
      {children}
    </motion.li>
  )
}

/* ---------- an illustration for the home page (synthetic, labelled as such) ---------- */

function rng(seed: number) {
  let s = seed
  return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646
}

export function illustrationDots(): { dots: UnpackDot[]; shown: number; mean: number; adjusted: number } {
  const rand = rng(42)
  const dots: UnpackDot[] = []
  const start = Date.UTC(2026, 0, 1)
  const pool = [5, 5, 4, 4, 4, 3, 3, 2, 1, 1]
  for (let i = 0; i < 52; i++) {
    const t = new Date(start + rand() * 230 * 86_400_000).toISOString().slice(0, 10)
    dots.push({ rating: pool[Math.floor(rand() * pool.length)], day: t, label: 'no_flags', single: rand() < 0.08 })
  }
  for (let i = 0; i < 30; i++) {
    const t = new Date(start + (150 + rand() * 3) * 86_400_000).toISOString().slice(0, 10)
    dots.push({ rating: 5, day: t, label: 'single_use_burst', single: true })
  }
  const avg = (xs: UnpackDot[]) => Math.round((xs.reduce((s, d) => s + d.rating, 0) / xs.length) * 100) / 100
  return { dots, shown: 4.6, mean: avg(dots), adjusted: avg(dots.filter((d) => d.label === 'no_flags')) }
}
