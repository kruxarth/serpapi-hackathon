import type { Label, Level, Verdict } from './types'

export const LABEL_TEXT: Record<Label, string> = {
  ring: 'Ring-like group',
  possible_ring_trip: 'Possible ring-like group (trip-like)',
  suspicious: 'Suspicious',
  group_trip: 'Trip or social group',
  no_flags: 'No flags',
  not_checked: 'Not checked',
}

export const LABEL_ORDER: Label[] = ['ring', 'possible_ring_trip', 'suspicious', 'group_trip', 'no_flags', 'not_checked']

export const VERDICT_TEXT: Record<Verdict, string> = {
  ring: 'Ring-like group',
  possible_ring: 'Possible ring-like group',
  possible_ring_trip: 'Possible ring-like group (trip-like pattern)',
  ruled_out_trip: 'Consistent with a group trip',
  social_circle: 'Consistent with friends or family',
  none: 'No verdict',
}

export const LEVEL_ICON: Record<Level, string> = {
  High: '▲',
  Elevated: '◆',
  Low: '●',
  'Not enough history': '○',
}

export const levelClass = (l: Level) => (l === 'Not enough history' ? 'NotEnough' : l)

/** Read a CSS custom property, for libraries (Cytoscape, Leaflet, Recharts) that need concrete colours. */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888'
}

export function labelColor(label: Label): string {
  switch (label) {
    case 'ring':
    case 'possible_ring_trip':
      return cssVar('--label-ring')
    case 'suspicious':
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

export function ageText(iso: string | null | undefined): string {
  if (!iso) return ''
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000
  if (days < 1) return 'today'
  if (days < 2) return 'yesterday'
  return `${Math.floor(days)} days ago`
}
