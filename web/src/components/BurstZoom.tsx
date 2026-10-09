// A burst of same-star reviews, zoomed: first the whole sample with the burst standing out, then the burst itself,
// one dot per review at its exact minute (India time). Drawn from the report's signals.T11 (minute offsets from the
// burst's start, never timestamps), so it works the same in presentation mode.

import { motion, useInView } from 'motion/react'
import { useMemo, useRef } from 'react'
import { day, istDay, istTime, spanText } from '../labels'
import { useWidth } from '../motion'
import type { Report, SameStarBurst } from '../types'
import { starFill } from './Reviewer'

const TOP = 64
const GAP = 34
const ZOOM = 104
const PAD = 14

export function BurstZoom({ report, burst, tone = 'var(--label-suspicious)' }: { report: Report; burst: SameStarBurst; tone?: string }) {
  const [box, W] = useWidth<HTMLDivElement>()
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -40px 0px' })
  const members = useMemo(() => new Set(burst.review_ids), [burst])

  // Whole sample: one bar per stretch of days, the burst's reviews in the tone colour.
  const overview = useMemo(() => {
    const dn = (d: string) => Date.parse(`${d.slice(0, 10)}T00:00:00Z`) / 86_400_000
    const rows = report.reviews.filter((r) => r.day)
    if (!rows.length) return null
    const first = Math.min(...rows.map((r) => dn(r.day!)))
    const last = Math.max(...rows.map((r) => dn(r.day!)))
    const bins = 64
    const per = Math.max(1, (last - first + 1) / bins)
    const total = new Array(bins).fill(0)
    const hot = new Array(bins).fill(0)
    rows.forEach((r) => {
      const b = Math.min(bins - 1, Math.floor((dn(r.day!) - first) / per))
      total[b]++
      if (members.has(r.review_id)) hot[b]++
    })
    const hotBins = hot.map((h, i) => (h ? i : -1)).filter((i) => i >= 0)
    return { bins, total, hot, max: Math.max(...total), from: Math.min(...hotBins), to: Math.max(...hotBins), first: rows.reduce((a, r) => (r.day! < a ? r.day! : a), rows[0].day!), last: rows.reduce((a, r) => (r.day! > a ? r.day! : a), rows[0].day!) }
  }, [report, members])

  // The burst: x by minutes after its start; dots that would overlap stack upwards.
  const span = Math.max(burst.minutes, 1)
  const x = (m: number) => PAD + (m / span) * (W - 2 * PAD)
  const dots = useMemo(() => {
    const lastX: number[] = []
    return burst.offsets.map((m) => {
      const px = PAD + (m / span) * (Math.max(W, 1) - 2 * PAD)
      let level = 0
      while (lastX[level] !== undefined && px - lastX[level] < 10) level++
      lastX[level] = px
      return { m, level }
    })
  }, [burst, span, W])
  const coreFrom = (Date.parse(burst.core.start) - Date.parse(burst.start)) / 60_000
  const coreTo = (Date.parse(burst.core.end) - Date.parse(burst.start)) / 60_000
  const showCore = burst.core.count < burst.count && burst.core.minutes < burst.minutes * 0.6
  const fill = starFill(burst.stars)
  const H = TOP + GAP + ZOOM + 30
  const colW = W / (overview?.bins ?? 1)

  return (
    <div ref={ref} className="burst-zoom">
      <div ref={box}>
        {W > 0 && overview && (
          <svg width={W} height={H} role="img" aria-label={`${burst.count} ${burst.stars}-star reviews in ${spanText(burst.minutes)}, out of the ${report.reviews.length} newest`}>
            {overview.total.map((n, i) => {
              const h = (n / overview.max) * (TOP - 14)
              const hh = (overview.hot[i] / overview.max) * (TOP - 14)
              return (
                <g key={i}>
                  {n > 0 && <rect x={i * colW + 1} y={TOP - h} width={Math.max(1, colW - 2)} height={h} rx={1.5} fill="var(--rule)" />}
                  {overview.hot[i] > 0 && (
                    <motion.rect x={i * colW + 1} width={Math.max(1, colW - 2)} rx={1.5} fill={tone}
                      initial={{ y: TOP, height: 0 }} animate={inView ? { y: TOP - hh, height: hh } : {}} transition={{ duration: 0.7, delay: 0.1 }} />
                  )}
                </g>
              )
            })}
            <text x={0} y={TOP + 12} className="bz-label">{day(overview.first)}</text>
            <text x={W} y={TOP + 12} textAnchor="end" className="bz-label">{day(overview.last)}</text>
            <motion.path
              d={`M${overview.from * colW},${TOP + 16} L${(overview.to + 1) * colW},${TOP + 16} L${W},${TOP + GAP} L0,${TOP + GAP} Z`}
              fill="var(--sunk)" initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ delay: 0.6, duration: 0.5 }} />
            <g transform={`translate(0, ${TOP + GAP})`}>
              <rect x={0} y={0} width={W} height={ZOOM} rx={10} fill="var(--sunk)" />
              <line x1={PAD} x2={W - PAD} y1={ZOOM - 14} y2={ZOOM - 14} stroke="var(--rule)" />
              {showCore && (
                <motion.g initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ delay: 1.1 + burst.count * 0.03 }}>
                  <path d={`M${x(coreFrom)},16 V10 H${x(coreTo)} V16`} fill="none" stroke={tone} strokeWidth={1.6} />
                  <text x={(x(coreFrom) + x(coreTo)) / 2} y={7} textAnchor="middle" className="bz-label strong" style={{ fill: tone }}>
                    {burst.core.count} within {spanText(burst.core.minutes)}
                  </text>
                </motion.g>
              )}
              {dots.map((d, i) => (
                <motion.circle key={i} cx={x(d.m)} cy={ZOOM - 22 - d.level * 10} r={4.4} fill={fill} stroke={tone} strokeWidth={1}
                  initial={{ opacity: 0, scale: 0 }} animate={inView ? { opacity: 1, scale: 1 } : {}}
                  transition={{ delay: 0.8 + i * 0.03, duration: 0.25 }} />
              ))}
            </g>
            <text x={PAD} y={H - 4} className="bz-label">{istTime(burst.start)}, {istDay(burst.start)}</text>
            <text x={W / 2} y={H - 4} textAnchor="middle" className="bz-label strong">{burst.count} reviews in {spanText(burst.minutes)}</text>
            <text x={W - PAD} y={H - 4} textAnchor="end" className="bz-label">{istTime(burst.end)}{istDay(burst.end) !== istDay(burst.start) ? `, ${istDay(burst.end)}` : ''} IST</text>
          </svg>
        )}
      </div>
    </div>
  )
}
