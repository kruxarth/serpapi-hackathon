import { Bar, BarChart, CartesianGrid, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useMemo } from 'react'
import { cssVar, LABEL_ORDER, LABEL_TEXT, labelColor } from '../labels'
import type { Label, Report } from '../types'

interface Props { report: Report; selectedGroup: string | null }

/** Bin start for a day: the day itself, or its Monday when the span is long enough to need weekly bars. */
function binOf(day: string, weekly: boolean): string {
  if (!weekly) return day
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7))
  return d.toISOString().slice(0, 10)
}

function bins(from: string, to: string, weekly: boolean): string[] {
  const out: string[] = []
  const d = new Date(`${binOf(from, weekly)}T00:00:00Z`)
  const end = new Date(`${to}T00:00:00Z`)
  while (d <= end && out.length < 2000) {
    out.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + (weekly ? 7 : 1))
  }
  return out
}

export function Timeline({ report, selectedGroup }: Props) {
  const members = useMemo(
    () => new Set(selectedGroup ? report.groups.find((g) => g.group_id === selectedGroup)?.members ?? [] : []),
    [report, selectedGroup],
  )
  const { data, labels, weekly } = useMemo(() => {
    const first = report.sample.first
    const last = report.sample.last
    if (!first || !last) return { data: [], labels: [] as Label[], weekly: false }
    const weekly = (Date.parse(last) - Date.parse(first)) / 86_400_000 > 200
    const rows = new Map(bins(first, last, weekly).map((d) => [d, { day: d, selected: 0 } as Record<string, number | string>]))
    const used = new Set<Label>()
    for (const r of report.reviews) {
      if (!r.day) continue
      const row = rows.get(binOf(r.day, weekly))
      if (!row) continue
      if (r.contributor_id && members.has(r.contributor_id)) {
        row.selected = (row.selected as number) + 1
      } else {
        row[r.label] = ((row[r.label] as number) ?? 0) + 1
        used.add(r.label)
      }
    }
    return { data: [...rows.values()], labels: LABEL_ORDER.filter((l) => used.has(l)), weekly }
  }, [report, members])

  if (!data.length) return <p className="muted">No dated reviews.</p>
  const grid = cssVar('--grid')
  const muted = cssVar('--muted')
  const ring = cssVar('--label-ring')
  const ink = cssVar('--ink')
  const bursts = report.signals.T1.bursts
  return (
    <div>
      <div style={{ height: 240 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }} barCategoryGap={1}>
            <defs>
              <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="6" height="6" fill={ring} fillOpacity={0.25} />
                <line x1="0" y1="0" x2="0" y2="6" stroke={ring} strokeWidth="3" />
              </pattern>
              <pattern id="hatch-blue" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="6" height="6" fill={cssVar('--label-suspicious')} fillOpacity={0.25} />
                <line x1="0" y1="0" x2="0" y2="6" stroke={cssVar('--label-suspicious')} strokeWidth="3" />
              </pattern>
            </defs>
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis dataKey="day" tick={{ fontSize: 11, fill: muted }} minTickGap={40} tickLine={false} axisLine={{ stroke: grid }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: muted }} tickLine={false} axisLine={false} />
            {bursts.map((b) => (
              <ReferenceArea key={b.start} x1={binOf(b.start, weekly)} x2={binOf(b.end, weekly)} fill={muted} fillOpacity={0.15} ifOverflow="extendDomain"
                label={{ value: `burst: ${b.count} in ${Math.round((Date.parse(b.end) - Date.parse(b.start)) / 86400000) + 1} days`, position: 'insideTop', fontSize: 11, fill: muted }} />
            ))}
            <Tooltip cursor={{ fill: grid, opacity: 0.5 }} content={({ active, payload, label }) =>
              active && payload?.length ? (
                <div className="tooltip" style={{ position: 'static' }}>
                  <strong>{label}</strong>
                  {payload.filter((p) => Number(p.value) > 0).map((p) => (
                    <div key={String(p.dataKey)}>{p.dataKey === 'selected' ? 'Selected group' : LABEL_TEXT[p.dataKey as Label]}: {String(p.value)}</div>
                  ))}
                </div>
              ) : null} />
            {labels.map((l) => (
              <Bar key={l} dataKey={l} stackId="a" fill={l === 'possible_ring_trip' ? 'url(#hatch)' : l === 'single_use_burst' ? 'url(#hatch-blue)' : labelColor(l)} isAnimationActive={false}
                fillOpacity={selectedGroup ? 0.35 : 1} stroke={cssVar('--surface')} strokeWidth={0.5} />
            ))}
            {selectedGroup && <Bar dataKey="selected" stackId="a" fill={ink} isAnimationActive={false} radius={[3, 3, 0, 0]} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        {labels.map((l) => <span key={l}><i className={`swatch ${l}`} /> {LABEL_TEXT[l]}</span>)}
        {selectedGroup && <span><i className="swatch" style={{ background: ink }} /> Selected group</span>}
        {bursts.length > 0 && <span><i className="swatch" style={{ background: muted, opacity: 0.4, borderRadius: 2 }} /> Review burst</span>}
        <span className="muted">Reviews per {weekly ? 'week' : 'day'} (IST){report.signals.T1.baseline_per_week ? `, normally about ${Math.max(1, Math.round(report.signals.T1.baseline_per_week))} a week` : ''}</span>
      </div>
    </div>
  )
}
