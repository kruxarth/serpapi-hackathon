import type { Label, Level, Verdict } from './types'

export const LABEL_TEXT: Record<Label, string> = {
  ring: 'Ring-like group',
  possible_ring_trip: 'Possible ring-like group (trip-like)',
  suspicious: 'Suspicious',
  single_use_burst: 'In a burst of same-star reviews',
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

/** How long a burst took, in the unit a reader would use ("89 minutes", "18 hours", "3 days"). Same as the backend. */
export function spanText(minutes: number): string {
  if (minutes < 120) {
    const n = Math.max(1, Math.round(minutes))
    return `${n} minute${n === 1 ? '' : 's'}`
  }
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)} hours`
  return `${Math.round(minutes / 1440)} days`
}

/** A listing's usual pace ("about one review every 18 days"). Same as the backend. */
export function paceText(perDay: number): string {
  if (perDay >= 1.5) return `about ${Math.round(perDay)} reviews a day`
  if (perDay >= 0.9) return 'about one review a day'
  const perWeek = perDay * 7
  if (perWeek >= 1.5) return `about ${Math.round(perWeek)} reviews a week`
  if (perWeek >= 0.9) return 'about one review a week'
  return perDay > 0 ? `about one review every ${Math.round(1 / perDay)} days` : 'almost no reviews'
}

const IST = 'Asia/Kolkata'
/** "17:47" in India time. */
export const istTime = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { timeZone: IST, hour: '2-digit', minute: '2-digit' })
/** "12 Sep 2023" in India time, written like `day()`. */
export const istDay = (iso: string) => day(new Date(iso).toLocaleDateString('en-CA', { timeZone: IST }))
/** "on 12 Sep 2023, 17:47 to 19:16" or "from 12 May 2025 16:54 to 13 May 2025 20:42". */
export function burstWhen(start: string, end: string): string {
  return istDay(start) === istDay(end)
    ? `on ${istDay(start)}, ${istTime(start)} to ${istTime(end)}`
    : `from ${istDay(start)} ${istTime(start)} to ${istDay(end)} ${istTime(end)}`
}

