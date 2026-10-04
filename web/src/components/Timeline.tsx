import { motion, useInView } from 'motion/react'
import { useId, useMemo, useRef, useState } from 'react'
import { day, dayCount, LABEL_ORDER, LABEL_TEXT } from '../labels'
import { useWidth } from '../motion'
import type { Label, Report } from '../types'

/** Bin start for a day: the day itself, or its Monday when the span is long enough to need weekly bars. */
function binOf(d: string, weekly: boolean): string {
  if (!weekly) return d
  const t = new Date(`${d}T00:00:00Z`)
  t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7))
  return t.toISOString().slice(0, 10)
}

interface Bin { start: string; counts: Partial<Record<Label, number>>; selected: number; total: number }

function shift(d: string, days: number): string {
  const t = new Date(`${d}T00:00:00Z`)
  t.setUTCDate(t.getUTCDate() + days)
  return t.toISOString().slice(0, 10)
}

function buildBins(report: Report, members: Set<string>, zoom?: Highlight) {
  // A zoomed view is daily, from three weeks before a burst to three weeks after (clipped to the sample).
  const first = zoom && report.sample.first ? [shift(zoom.start, -21), report.sample.first].sort()[1] : report.sample.first
  const last = zoom && report.sample.last ? [shift(zoom.end, 21), report.sample.last].sort()[0] : report.sample.last
  if (!first || !last) return { bins: [] as Bin[], weekly: false, labels: [] as Label[] }
  const weekly = !zoom && dayCount(first, last) > 200
  const bins: Bin[] = []
  const index = new Map<string, Bin>()
  const d = new Date(`${binOf(first, weekly)}T00:00:00Z`)
  const end = new Date(`${last}T00:00:00Z`)
  while (d <= end && bins.length < 2000) {
    const b: Bin = { start: d.toISOString().slice(0, 10), counts: {}, selected: 0, total: 0 }
    bins.push(b)
    index.set(b.start, b)
    d.setUTCDate(d.getUTCDate() + (weekly ? 7 : 1))
  }
  const used = new Set<Label>()
  for (const r of report.reviews) {
    if (!r.day) continue
    const b = index.get(binOf(r.day, weekly))
    if (!b) continue
    b.total += 1
    if (r.contributor_id && members.has(r.contributor_id)) b.selected += 1
    else {
      b.counts[r.label] = (b.counts[r.label] ?? 0) + 1
      used.add(r.label)
    }
  }
  return { bins, weekly, labels: LABEL_ORDER.filter((l) => used.has(l)) }
}

export interface Highlight { start: string; end: string; text: string; tone: 'suspicious' | 'neutral' }

interface Props {
  report: Report
  selectedGroup?: string | null
  highlights?: Highlight[]
  height?: number
  legend?: boolean
  /** Show only the weeks around this one highlight, by day. */
  zoom?: boolean
}

export function Timeline({ report, selectedGroup = null, highlights, height = 240, legend = true, zoom = false }: Props) {
  const uid = useId().replace(/:/g, '')
  const [box, width] = useWidth<HTMLDivElement>()
  const seen = useRef<HTMLDivElement>(null)
  const inView = useInView(seen, { once: true, margin: '0px 0px -60px 0px' })
  const [hover, setHover] = useState<number | null>(null)
  const members = useMemo(
    () => new Set(selectedGroup ? report.groups.find((g) => g.group_id === selectedGroup)?.members ?? [] : []),
    [report, selectedGroup],
  )
  const focus = zoom ? highlights?.[0] : undefined
  const { bins, weekly, labels } = useMemo(() => buildBins(report, members, focus), [report, members, focus])
  const marks: Highlight[] = highlights ?? report.signals.T1.bursts.map((b) => ({
    start: b.start, end: b.end, text: `${b.count} in ${dayCount(b.start, b.end)} days`, tone: 'neutral',
  }))

  if (!bins.length) return <p className="muted">No dated reviews.</p>

  const top = 26
  const bottom = 24
  const plotH = height - top - bottom
  const max = Math.max(1, ...bins.map((b) => b.total))
  const left = 30
  const step = (width - left) / bins.length
  const barW = Math.max(1, step - (step > 4 ? Math.min(2, step * 0.25) : 0))
  const y = (v: number) => (v / max) * plotH
  const idx = new Map(bins.map((b, i) => [b.start, i]))
  const fill = (l: Label) =>
    l === 'possible_ring_trip' ? `url(#${uid}-hr)` : l === 'single_use_burst' ? `url(#${uid}-hb)` : `var(--label-${l === 'ring' ? 'ring' : l === 'suspicious' ? 'suspicious' : l === 'group_trip' ? 'trip' : l === 'not_checked' ? 'unchecked' : 'none'})`
  const ticks = Math.max(2, Math.floor(width / 140))
  const tickEvery = Math.max(1, Math.ceil(bins.length / ticks))
  const tickText = (s: string) => {
    const [dd, mm, yy] = day(s).split(' ')
    return weekly ? `${mm} ${yy}` : `${dd} ${mm}`
  }
  const grid = [Math.round(max / 2), max].filter((v, i, a) => v > 0 && a.indexOf(v) === i)
  const hb = hover != null ? bins[hover] : null

  return (
    <div ref={seen}>
      <div ref={box} style={{ position: 'relative' }}>
        {width > 0 && (
          <svg width={width} height={height} role="img" aria-label={`Reviews per ${weekly ? 'week' : 'day'}`}
            onMouseMove={(e) => {
              const x = e.clientX - e.currentTarget.getBoundingClientRect().left
              setHover(Math.min(bins.length - 1, Math.max(0, Math.floor((x - left) / step))))
            }}
            onMouseLeave={() => setHover(null)}>
            <defs>
              <pattern id={`${uid}-hr`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="5" height="5" fill="var(--label-ring)" fillOpacity="0.3" /><line x1="0" y1="0" x2="0" y2="5" stroke="var(--label-ring)" strokeWidth="3" />
              </pattern>
              <pattern id={`${uid}-hb`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="5" height="5" fill="var(--label-suspicious)" fillOpacity="0.3" /><line x1="0" y1="0" x2="0" y2="5" stroke="var(--label-suspicious)" strokeWidth="3" />
              </pattern>
            </defs>
            {grid.map((g) => (
              <g key={g}>
                <line x1={left} x2={width} y1={top + plotH - y(g)} y2={top + plotH - y(g)} stroke="var(--grid)" strokeDasharray="2 4" />
                <text x={left - 8} y={top + plotH - y(g) + 4} textAnchor="end" fontSize="10.5" fill="var(--muted)" className="num">{g}</text>
              </g>
            ))}
            {marks.map((m, i) => {
              const a = idx.get(binOf(m.start, weekly))
              const b = idx.get(binOf(m.end, weekly))
              if (a === undefined || b === undefined) return null
              const x = left + a * step - 3
              const w = (b - a + 1) * step + 6
              const color = m.tone === 'suspicious' ? 'var(--label-suspicious)' : 'var(--ink)'
              return (
                <motion.g key={`${m.start}-${i}`} initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ delay: 0.9 + i * 0.15, duration: 0.6 }}>
                  <rect x={x} y={top - 4} width={w} height={plotH + 4} rx={4} fill={color} fillOpacity={m.tone === 'suspicious' ? 0.1 : 0.05} />
                  <text x={Math.min(Math.max(x + w / 2, 50), width - 50)} y={top - 10} textAnchor="middle" fontSize="11" fontWeight="600" fill={m.tone === 'suspicious' ? 'var(--label-suspicious)' : 'var(--ink-2)'}>{m.text}</text>
                </motion.g>
              )
            })}
            {bins.map((b, i) => {
              let acc = 0
              const segs = labels.map((l) => {
                const v = b.counts[l] ?? 0
                const h = y(v)
                const seg = v ? <rect key={l} x={left + i * step} y={top + plotH - acc - h} width={barW} height={h} fill={fill(l)} fillOpacity={selectedGroup ? 0.3 : 1} rx={barW > 4 ? 1.5 : 0} /> : null
                acc += h
                return seg
              })
              const sel = b.selected ? <rect key="sel" x={left + i * step} y={top + plotH - acc - y(b.selected)} width={barW} height={y(b.selected)} fill="var(--ink)" rx={barW > 4 ? 1.5 : 0} /> : null
              if (!b.total) return null
              return (
                <motion.g key={b.start} style={{ originY: 1, transformBox: 'fill-box' }} initial={{ scaleY: 0 }} animate={inView ? { scaleY: 1 } : {}}
                  transition={{ type: 'spring', stiffness: 140, damping: 18, delay: Math.min(0.9, i * (0.9 / bins.length)) }}>
                  {segs}{sel}
                </motion.g>
              )
            })}
            <line x1={left} x2={width} y1={top + plotH + 0.5} y2={top + plotH + 0.5} stroke="var(--line-strong)" />
            {bins.map((b, i) => (i % tickEvery === 0 ? (
              <text key={b.start} x={left + i * step} y={height - 6} fontSize="10.5" fill="var(--muted)">{tickText(b.start)}</text>
            ) : null))}
            {hb && <rect x={left + hover! * step} y={top} width={barW} height={plotH} fill="var(--ink)" fillOpacity={0.05} pointerEvents="none" />}
          </svg>
        )}
        {hb && hb.total > 0 && (
          <div className="tooltip" style={{ left: Math.min(left + hover! * step + 14, width - 220), top: 8 }}>
            <strong>{weekly ? `Week of ${day(hb.start)}` : day(hb.start)}</strong>
            {labels.filter((l) => hb.counts[l]).map((l) => <div key={l} className="row" style={{ gap: 6 }}><i className={`swatch ${l}`} />{LABEL_TEXT[l]}: <span className="num">{hb.counts[l]}</span></div>)}
            {hb.selected > 0 && <div>Selected group: <span className="num">{hb.selected}</span></div>}
          </div>
        )}
      </div>
      {legend && (
        <div className="legend" style={{ marginTop: 14 }}>
          {labels.map((l) => <span key={l}><i className={`swatch ${l}`} /> {LABEL_TEXT[l]}</span>)}
          {selectedGroup && <span><i className="swatch" style={{ background: 'var(--ink)' }} /> Selected group</span>}
          {marks.length > 0 && <span><i className="swatch" style={{ background: 'var(--ink)', opacity: 0.12, borderRadius: 3 }} /> Review burst</span>}
          <span className="muted">
            Reviews per {weekly ? 'week' : 'day'} (IST)
            {report.signals.T1.baseline_per_week ? `, normally about ${Math.max(1, Math.round(report.signals.T1.baseline_per_week))} a week` : ''}
          </span>
        </div>
      )}
    </div>
  )
}
