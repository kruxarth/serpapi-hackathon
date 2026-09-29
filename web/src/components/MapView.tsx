import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { useEffect, useMemo } from 'react'
import { cssVar } from '../labels'
import type { Namer } from '../names'
import type { Report } from '../types'

interface Props {
  report: Report
  namer: Namer
  selectedGroup: string | null
  presentation: boolean
}

interface Pt { key: string; lat: number; lng: number; name: string; groups: string[]; core: boolean; members: number; area: string | null }

/** A gentle arc between two points (quadratic Bézier), so same-day pairs read as links, not roads. */
function arc(a: [number, number], b: [number, number]): [number, number][] {
  const mid: [number, number] = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const dx = b[1] - a[1]
  const dy = b[0] - a[0]
  const ctrl: [number, number] = [mid[0] + dx * 0.2, mid[1] - dy * 0.2]
  const out: [number, number][] = []
  for (let i = 0; i <= 24; i++) {
    const t = i / 24
    out.push([
      (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * b[0],
      (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * b[1],
    ])
  }
  return out
}

function Fit({ points }: { points: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length === 1) map.setView(points[0], 9)
    else if (points.length > 1) map.fitBounds(points, { padding: [30, 30] })
  }, [map, points])
  return null
}

export function MapView({ report, namer, selectedGroup, presentation }: Props) {
  const ring = cssVar('--label-ring')
  const trip = cssVar('--label-trip')
  const ink = cssVar('--ink')
  const accent = cssVar('--accent')

  const { points, target, arcs } = useMemo(() => {
    const pts = new Map<string, Pt>()
    for (const [gid, rows] of Object.entries(report.client_lists)) {
      if (selectedGroup && gid !== selectedGroup) continue
      for (const r of rows) {
        if (r.lat == null || r.lng == null) continue
        const p = pts.get(r.place_key) ?? { key: r.place_key, lat: r.lat, lng: r.lng, name: namer.place(r.place_key), groups: [], core: false, members: 0, area: r.area }
        p.groups.push(gid)
        p.core ||= r.core
        p.members = Math.max(p.members, r.member_count)
        pts.set(r.place_key, p)
      }
    }
    const t = report.place.lat != null && report.place.lng != null ? ([report.place.lat, report.place.lng] as [number, number]) : null
    const members = selectedGroup ? new Set(report.groups.find((g) => g.group_id === selectedGroup)?.members ?? []) : null
    const arcList: { from: [number, number]; to: [number, number]; day: string; km: number }[] = []
    for (const r of report.reviewers) {
      if (members && !members.has(r.contributor_id)) continue
      const a4 = r.badges.find((b) => b.code === 'A4')
      for (const occ of (a4?.occasions as { day: string; places: string[]; km: number }[] | undefined) ?? []) {
        const [p1, p2] = occ.places.map((k) => report.places[k])
        if (p1?.lat != null && p1.lng != null && p2?.lat != null && p2.lng != null) {
          arcList.push({ from: [p1.lat, p1.lng], to: [p2.lat, p2.lng], day: occ.day, km: occ.km })
        }
      }
    }
    return { points: [...pts.values()], target: t, arcs: arcList }
  }, [report, namer, selectedGroup])

  const bounds = useMemo(() => {
    const b: [number, number][] = points.map((p) => [p.lat, p.lng])
    if (target) b.push(target)
    return b
  }, [points, target])

  if (!target && points.length === 0) {
    return <div className="map-box muted" style={{ display: 'grid', placeItems: 'center' }}>No locations to show.</div>
  }
  return (
    <div>
      <div className="map-box">
        <MapContainer center={target ?? [22.5, 79]} zoom={5} maxZoom={presentation ? 11 : 18} style={{ height: '100%' }} scrollWheelZoom={false}>
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={presentation ? 11 : 18} />
          <Fit points={bounds} />
          {arcs.map((a, i) => (
            <Polyline key={i} positions={arc(a.from, a.to)} pathOptions={{ color: accent, weight: 2, dashArray: '4 4', opacity: 0.8 }}>
              <Tooltip sticky>Same-day reviews {a.km} km apart · {a.day}</Tooltip>
            </Polyline>
          ))}
          {points.map((p) => {
            const g = report.groups.find((x) => x.group_id === p.groups[0])
            const color = g?.verdict === 'ruled_out_trip' ? trip : ring
            return (
              <CircleMarker key={p.key} center={[p.lat, p.lng]} radius={4 + Math.min(p.members, 10)}
                pathOptions={{ color, fillColor: color, fillOpacity: p.core ? 0.75 : 0.3, weight: 2, dashArray: g?.verdict === 'possible_ring_trip' ? '3 3' : undefined }}>
                <Tooltip>
                  <strong>{p.name}</strong><br />{p.area ?? 'Unknown area'} · reviewed by {p.members} group members{p.core ? ' (core place)' : ''}
                </Tooltip>
              </CircleMarker>
            )
          })}
          {target && (
            <CircleMarker center={target} radius={9} pathOptions={{ color: ink, fillColor: ink, fillOpacity: 0.9, weight: 2 }}>
              <Tooltip permanent direction="top" offset={[0, -8]}>{namer.place(report.place.place_key)}</Tooltip>
            </CircleMarker>
          )}
        </MapContainer>
      </div>
      <div className="legend">
        <span><i className="swatch" style={{ background: ink }} /> This business</span>
        {points.length > 0 && <span><i className="swatch ring" /> Places the group reviewed (size = members)</span>}
        {points.length === 0 && <span className="muted">No flagged group, so no other places to map.</span>}
        {arcs.length > 0 && <span style={{ color: accent }}>– – Same-day reviews far apart (context only; people do travel)</span>}
        {presentation && <span className="muted">Locations rounded; zoom limited to city level</span>}
      </div>
    </div>
  )
}
