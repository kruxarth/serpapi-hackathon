// Shared by the service worker, side panel and options page (all extension pages with host permissions).
// The content script never calls the backend: google.com pages can't reach localhost.

export interface ExtSettings {
  backendUrl: string
  presentation: boolean
}

export const DEFAULTS: ExtSettings = { backendUrl: 'http://127.0.0.1:8765', presentation: false }

export async function getSettings(): Promise<ExtSettings> {
  const stored = await chrome.storage.local.get(['backendUrl', 'presentation'])
  return { ...DEFAULTS, ...stored } as ExtSettings
}

export interface Summary {
  level: string
  headline: string | null
  reasons: string[]
  title: string | null
  rating: number | null
  sample_mean: number | null
  adjusted: number | null
  examined: number
  rings: number
  evidence: string[]
  kept_mean?: number | null
  kept_count?: number | null
  signs?: Record<string, number>
}

export type Lookup =
  | { state: 'found'; analysisId: string; ageDays: number; summary: Summary }
  | { state: 'none'; dataId?: string }
  | { state: 'demo'; message: string }
  | { state: 'down' }
  | { state: 'no_place' }
  | { state: 'needs_lookup'; query?: string } // a share.google link: it names the place, a lookup finds it

export interface TabPlace {
  url: string
  dataId: string | null
  lookup?: Lookup
}

export async function backend<T>(path: string, init?: RequestInit): Promise<T> {
  const { backendUrl } = await getSettings()
  const resp = await fetch(`${backendUrl.replace(/\/$/, '')}${path}`, init)
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      detail = (await resp.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return backend<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-ReviewRing': '1' },
    body: JSON.stringify(body),
  })
}

export async function lookupPlace(url: string): Promise<Lookup> {
  const { presentation } = await getSettings()
  try {
    const r = await backend<{
      found: boolean
      reason?: string
      message?: string
      analysis_id?: string
      age_days?: number
      summary?: Summary
      data_id?: string
      query?: string
    }>(`/api/places/latest?url=${encodeURIComponent(url)}&presentation=${presentation ? 1 : 0}`)
    if (r.found && r.summary && r.analysis_id) {
      return { state: 'found', analysisId: r.analysis_id, ageDays: r.age_days ?? 0, summary: r.summary }
    }
    if (r.reason === 'demo') return { state: 'demo', message: r.message ?? '' }
    if (r.reason === 'no_place') return { state: 'no_place' }
    if (r.reason === 'needs_lookup') return { state: 'needs_lookup', query: r.query }
    return { state: 'none', dataId: r.data_id }
  } catch (e) {
    if (e instanceof TypeError) return { state: 'down' } // fetch failed: backend not running
    return { state: 'down' }
  }
}

export const tabKey = (tabId: number) => `tab:${tabId}`
