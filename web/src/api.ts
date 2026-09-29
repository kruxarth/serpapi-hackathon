// All network calls go to the local backend. Mutating calls carry the X-ReviewRing header,
// which the backend requires (it forces a CORS preflight that only this app passes).

import type {
  AnalysisDetail,
  AnalysisListItem,
  Budget,
  Estimate,
  Health,
  ResolveResult,
  Settings,
} from './types'

export class ApiError extends Error {
  status: number
  kind?: string
  constructor(status: number, message: string, kind?: string) {
    super(message)
    this.status = status
    this.kind = kind
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response
  try {
    resp = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'The ReviewRing backend is not running. Start it with: uv run reviewring serve')
  }
  if (!resp.ok) {
    let detail = resp.statusText
    let kind: string | undefined
    try {
      const body = await resp.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      kind = body.kind
    } catch {
      /* not JSON */
    }
    if (resp.status === 502 || resp.status === 504) {
      throw new ApiError(0, 'The ReviewRing backend is not running. Start it with: uv run reviewring serve')
    }
    throw new ApiError(resp.status, detail, kind)
  }
  return resp.json() as Promise<T>
}

function send<T>(method: 'POST' | 'PUT', path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-ReviewRing': '1' },
    body: JSON.stringify(body ?? {}),
  })
}

const q = (presentation: boolean) => (presentation ? '?presentation=1' : '?presentation=0')

export interface StartOptions {
  n?: number
  k1?: number
  k2?: number
  stop_after_round1?: boolean
  pick?: string
}

export const api = {
  health: () => request<Health>('/api/health'),
  budget: () => request<Budget>('/api/budget'),
  settings: () => request<Settings>('/api/settings'),
  saveSettings: (changes: Partial<Settings>) => send<Settings>('PUT', '/api/settings', changes),
  resolve: (input: string, opts: StartOptions & { confirm_lookup?: boolean }) =>
    send<ResolveResult>('POST', '/api/resolve', { input, ...opts }),
  dryRun: (input: string, opts: StartOptions) =>
    send<{ dry_run: true; estimate: Estimate }>('POST', '/api/analyses', { input, ...opts, dry_run: true }),
  start: (input: string, opts: StartOptions) =>
    send<{ analysis_id: string; estimate: Estimate }>('POST', '/api/analyses', { input, ...opts }),
  list: (presentation: boolean) => request<AnalysisListItem[]>(`/api/analyses${q(presentation)}`),
  get: (id: string, presentation: boolean) =>
    request<AnalysisDetail>(`/api/analyses/${encodeURIComponent(id)}${q(presentation)}`),
  resume: (id: string, pick?: string) =>
    send<{ analysis_id: string }>('POST', `/api/analyses/${encodeURIComponent(id)}/resume`, { pick }),
  cancel: (id: string) => send<{ cancelled: boolean }>('POST', `/api/analyses/${encodeURIComponent(id)}/cancel`, {}),
  exportFixture: (id: string) => send<{ fixture: string }>('POST', `/api/analyses/${encodeURIComponent(id)}/export`, {}),
  evaluation: () => request<Record<string, unknown> & { available: boolean }>('/api/evaluation'),
  eventsUrl: (id: string) => `/api/analyses/${encodeURIComponent(id)}/events`,
}
