import type { Label, Level, Verdict } from './types'

export const LABEL_TEXT: Record<Label, string> = {
  ring: 'Ring-like group',
  possible_ring_trip: 'Possible ring-like group (trip-like)',
  suspicious: 'Suspicious',
  single_use_burst: 'First-time account in a burst',
  group_trip: 'Trip or social group',
  no_flags: 'No flags',
  not_checked: 'Not checked',
}

export const LABEL_ORDER: Label[] = ['ring', 'possible_ring_trip', 'suspicious', 'single_use_burst', 'group_trip', 'no_flags', 'not_checked']

export const VERDICT_TEXT: Record<Verdict, string> = {
  ring: 'Ring-like group',
  possible_ring: 'Possible ring-like group',
  possible_ring_trip: 'Possible ring-like group (trip-like pattern)',
  ruled_out_trip: 'Consistent with a group trip',
  social_circle: 'Consistent with friends or family',
  none: 'No verdict',
}

export const BADGE_NAMES: Record<string, string> = {
  A1: 'Thin profile', A2: 'Rating monotony', A3: 'Several cities in one week', A4: 'Same-day distant reviews',
  A5: 'Short texts', A6: 'Copy-paste text', A7: 'Burst participant', A8: 'Reworded template (AI)', A9: 'Reviewing spree',
}

export const FLAGGED_VERDICTS: Verdict[] = ['ring', 'possible_ring', 'possible_ring_trip']

export const levelClass = (l: Level) => `lvl-${l === 'Not enough history' ? 'NotEnough' : l}`

/** Read a CSS custom property, for libraries (Cytoscape, Leaflet) that need concrete colours. */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888'
}

export function labelColor(label: Label): string {
  switch (label) {
    case 'ring':
    case 'possible_ring_trip':
      return cssVar('--label-ring')
    case 'suspicious':
    case 'single_use_burst':
      return cssVar('--label-suspicious')
    case 'group_trip':
      return cssVar('--label-trip')
    case 'not_checked':
      return cssVar('--label-unchecked')
    default:
      return cssVar('--label-none')
  }
}

export const fmt = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '–' : v.toFixed(digits)

export const pct = (share: number) => `${Math.round(share * 100)}%`

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2023-03-19" → "19 Mar 2023"; the day itself is not changed. */
export function day(iso: string | null | undefined): string {
  if (!iso) return '–'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`
}

export function dayCount(start: string, end: string): number {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1
}

export function ageText(iso: string | null | undefined): string {
  if (!iso) return ''
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000
  if (days < 1) return 'today'
  if (days < 2) return 'yesterday'
  return `${Math.floor(days)} days ago`
}
