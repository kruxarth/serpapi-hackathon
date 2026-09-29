import type { Report } from './types'

/** Display names for reviewers and places: pseudonyms in presentation mode, real names otherwise. */
export function makeNamer(report: Report) {
  const reviewer = new Map<string, string>()
  let n = 0
  const add = (id: string | null | undefined, display?: string) => {
    if (!id || reviewer.has(id)) return
    n += 1
    reviewer.set(id, display ?? report.names?.[id] ?? `Reviewer ${n}`)
  }
  report.reviewers.forEach((r) => add(r.contributor_id, r.display_name))
  report.reviews.forEach((r) => add(r.contributor_id, r.display_name))
  const place = (key: string): string => {
    if (key === report.place.place_key) return report.place.title ?? 'This business'
    const p = report.places[key]
    if (p?.title) return p.title
    for (const rows of Object.values(report.client_lists)) {
      const row = rows.find((r) => r.place_key === key)
      if (row?.title) return row.title
    }
    return 'Place'
  }
  return { reviewer: (id: string | null | undefined) => (id ? reviewer.get(id) ?? 'Reviewer' : 'Anonymous'), place }
}
export type Namer = ReturnType<typeof makeNamer>
