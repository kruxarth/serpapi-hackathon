import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import { useEffect, useMemo, useRef, useState } from 'react'
import { cssVar, LABEL_ORDER, LABEL_TEXT, labelColor, VERDICT_TEXT } from '../labels'
import type { Namer } from '../names'
import type { Label, Report } from '../types'

cytoscape.use(fcose)

interface Props {
  report: Report
  namer: Namer
  selectedGroup: string | null
  onSelectGroup: (g: string | null) => void
}

export function RingGraph({ report, namer, selectedGroup, onSelectGroup }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const cy = useRef<Core | null>(null)
  const [showPlaces, setShowPlaces] = useState(false)
  const [tip, setTip] = useState<{ x: number; y: number; html: string[] } | null>(null)

  const elements = useMemo(() => buildElements(report, namer, showPlaces), [report, namer, showPlaces])

  useEffect(() => {
    if (!box.current) return
    const ink = cssVar('--ink')
    const muted = cssVar('--muted')
    const ring = cssVar('--label-ring')
    const surface = cssVar('--surface')
    const instance = cytoscape({
      container: box.current,
      elements,
      wheelSensitivity: 0.2,
      maxZoom: 1.6,
      style: [
        { selector: 'node.person', style: {
          'background-color': 'data(color)', width: 18, height: 18, label: 'data(name)', 'font-size': 9,
          color: ink, 'text-valign': 'bottom', 'text-margin-y': 3, 'border-width': 2, 'border-color': surface } },
        { selector: 'node.person.hollow', style: { 'background-color': surface, 'border-color': 'data(color)', 'border-width': 2 } },
        { selector: 'node.person.dashed', style: { 'border-style': 'dashed', 'background-color': surface, 'border-color': ring, 'border-width': 3 } },
        { selector: 'node.place', style: { shape: 'round-rectangle', width: 12, height: 12, 'background-color': muted,
          label: 'data(name)', 'font-size': 8, color: muted, 'text-valign': 'top', 'text-margin-y': -2 } },
        { selector: 'node.group', style: { 'background-opacity': 0.04, 'background-color': 'data(color)', 'border-color': 'data(color)',
          'border-width': 2, shape: 'round-rectangle', label: 'data(name)', 'font-size': 10, color: ink,
          'text-valign': 'top', 'text-halign': 'center', padding: '14px' } },
        { selector: 'node.group.possible', style: { 'border-style': 'dashed', 'border-width': 1.5 } },
        { selector: 'node.group.trip', style: { 'border-style': 'dotted' } },
        { selector: 'edge', style: { width: 'data(width)', 'line-color': muted, opacity: 0.55, 'curve-style': 'straight' } },
        { selector: 'edge.visit', style: { width: 1, 'line-style': 'dotted', opacity: 0.45 } },
        { selector: '.faded', style: { opacity: 0.12 } },
      ],
      layout: { name: 'fcose', randomize: true, seed: 7, animate: false, nodeRepulsion: 6000, idealEdgeLength: 70, packComponents: true } as cytoscape.LayoutOptions,
    })
    instance.on('mouseover', 'node.person', (e) => {
      const d = e.target.data()
      const p = e.renderedPosition
      setTip({ x: p.x, y: p.y, html: [d.fullName, LABEL_TEXT[d.label as Label], ...(d.badges as string[])] })
    })
    instance.on('mouseover', 'edge', (e) => {
      const d = e.target.data()
      if (!d.shared) return
      const p = e.target.renderedMidpoint()
      setTip({ x: p.x, y: p.y, html: [`Pair weight ${d.weight.toFixed(2)}`, `${d.shared} shared places`] })
    })
    instance.on('mouseover', 'node.place', (e) => {
      const p = e.renderedPosition
      setTip({ x: p.x, y: p.y, html: [e.target.data('name')] })
    })
    instance.on('mouseout', () => setTip(null))
    instance.on('tap', 'node.group', (e) => onSelectGroup(e.target.data('gid')))
    instance.on('tap', 'node.person', (e) => onSelectGroup(e.target.data('group') ?? null))
    instance.on('tap', (e) => {
      if (e.target === instance) onSelectGroup(null)
    })
    cy.current = instance
    return () => instance.destroy()
  }, [elements, onSelectGroup])

  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.elements().removeClass('faded')
    if (!selectedGroup) return
    const keep = c.nodes().filter((n) => n.data('group') === selectedGroup || n.data('gid') === selectedGroup || (n.hasClass('place') && n.data('groups')?.includes(selectedGroup)))
    c.elements().not(keep).not(keep.connectedEdges()).addClass('faded')
  }, [selectedGroup, elements])

  const present = LABEL_ORDER.filter((l) => report.graph.nodes.some((n) => n.label === l))
  return (
    <div>
      <div className="row small" style={{ marginBottom: 8 }}>
        <label className="toggle">
          <input type="checkbox" checked={showPlaces} onChange={(e) => setShowPlaces(e.target.checked)} /> Show shared places as nodes
        </label>
        <span className="muted">Each dot is a reviewer whose history was checked. A line joins two reviewers who reviewed the same unrelated, distant places.</span>
      </div>
      <div style={{ position: 'relative' }}>
        <div ref={box} className="graph-box" role="img" aria-label="Graph of reviewers connected by shared places" />
        {tip && (
          <div className="tooltip" style={{ left: tip.x + 12, top: tip.y + 12 }}>
            <strong>{tip.html[0]}</strong>
            {tip.html.slice(1).map((l) => <div key={l}>{l}</div>)}
          </div>
        )}
        {report.graph.nodes.length === 0 && (
          <div className="muted" style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
            No reviewer histories to show.
          </div>
        )}
        {report.graph.nodes.length > 0 && report.graph.edges.length === 0 && (
          <div className="muted small" style={{ position: 'absolute', left: 12, right: 12, bottom: 10, textAlign: 'center' }}>
            None of the {report.graph.nodes.length} reviewers checked share any other places: no linked groups.
          </div>
        )}
      </div>
      <div className="legend">
        {present.map((l) => <span key={l}><i className={`swatch ${l}`} /> {LABEL_TEXT[l]}</span>)}
        <span className="muted">Outlines: solid = ring-like group, dashed = possible, dotted = ruled out (trip or friends)</span>
      </div>
    </div>
  )
}

function buildElements(report: Report, namer: Namer, showPlaces: boolean): ElementDefinition[] {
  const els: ElementDefinition[] = []
  const inGroup = new Map<string, string>()
  const shown = report.groups.filter((g) => g.verdict !== 'none')
  for (const g of shown) {
    const kind = g.verdict === 'ring' || g.verdict === 'possible_ring' ? 'ring' : g.verdict === 'possible_ring_trip' ? 'possible' : 'trip' // trip covers social circles too
    const color = kind === 'trip' ? cssVar('--label-trip') : cssVar('--label-ring')
    els.push({ data: { id: `group:${g.group_id}`, gid: g.group_id, name: `${g.group_id} · ${VERDICT_TEXT[g.verdict]}`, color },
      classes: `group ${kind}` })
    g.members.forEach((m) => inGroup.set(m, g.group_id))
  }
  const badgesOf = new Map(report.reviewers.map((r) => [r.contributor_id, r.badges.map((b) => b.name)]))
  for (const n of report.graph.nodes) {
    const gid = inGroup.get(n.id)
    const classes = ['person']
    if (n.label === 'possible_ring_trip') classes.push('dashed')
    if (n.label === 'not_checked') classes.push('hollow')
    els.push({ data: { id: n.id, name: gid ? namer.reviewer(n.id) : '', fullName: namer.reviewer(n.id), label: n.label, color: labelColor(n.label), group: gid ?? null,
      badges: badgesOf.get(n.id) ?? [], parent: gid ? `group:${gid}` : undefined }, classes: classes.join(' ') })
  }
  for (const e of report.graph.edges) {
    els.push({ data: { id: `e:${e.source}:${e.target}`, source: e.source, target: e.target, weight: e.weight,
      width: Math.min(1 + e.weight * 0.8, 7), shared: e.shared.length } })
  }
  if (showPlaces) {
    const placeGroups = new Map<string, string[]>()
    for (const [gid, rows] of Object.entries(report.client_lists)) {
      for (const row of rows) {
        placeGroups.set(row.place_key, [...(placeGroups.get(row.place_key) ?? []), gid])
        if (!els.some((x) => x.data.id === `place:${row.place_key}`)) {
          els.push({ data: { id: `place:${row.place_key}`, name: row.title ?? 'Place', groups: [] as string[] }, classes: 'place' })
        }
        for (const m of row.members) {
          els.push({ data: { id: `v:${m}:${row.place_key}`, source: m, target: `place:${row.place_key}`, width: 1 }, classes: 'visit' })
        }
      }
    }
    for (const el of els) {
      const key = String(el.data.id).startsWith('place:') ? String(el.data.id).slice(6) : null
      if (key) el.data.groups = placeGroups.get(key)
    }
  }
  return els
}
