// Shapes of the backend's JSON. Kept in one place so the views stay honest about what they read.

export type Level = 'High' | 'Elevated' | 'Low' | 'Not enough history'
export type Label = 'ring' | 'possible_ring_trip' | 'suspicious' | 'group_trip' | 'no_flags' | 'not_checked'
export type Verdict = 'ring' | 'possible_ring' | 'possible_ring_trip' | 'ruled_out_trip' | 'none'

export interface Health {
  status: string
  mode: Mode
  algorithm_version: string
  serpapi_key_set: boolean
  deepseek_key_set: boolean
}

export type Mode = 'live' | 'offline' | 'demo'

export interface Budget {
  mode: Mode
  month_remaining: number
  hour_remaining: number
  monthly_cap: number
  hourly_cap: number
  per_analysis_cap: number
  ledger_month: number
  ledger_hour: number
  hour_resume_at: string | null
  note: string | null
  account: Record<string, unknown> | null
}

export interface Estimate {
  min: number
  max: number
  lines: string[]
  cap: number
}

export interface Candidate {
  data_id: string | null
  title: string | null
  address: string | null
  type: string | null
  rating: number | null
  reviews: number | null
}

export interface ResolveResult {
  resolved: { kind: string; cost: number; data_id?: string }
  needs_confirmation?: boolean
  lookup_cost?: number
  candidates?: Candidate[]
  estimate: Estimate
}

export interface AnalysisListItem {
  id: string
  status: string
  stage: string | null
  searches_used: number
  started_at: string | null
  finished_at: string | null
  input: string | null
  title: string | null
  type: string | null
  area: string | null
  level: Level | null
  adjusted?: number | null
  sample_mean?: number | null
  synthetic?: boolean
}

export interface ProgressEvent {
  type: string
  message: string
  searches_used: number
  data: Record<string, unknown>
  at?: string
}

export interface Badge {
  code: string
  name: string
  [k: string]: unknown
}

export interface ReviewerRow {
  contributor_id: string
  display_name?: string
  round: number
  reason: 'priority' | 'baseline'
  status: string
  label: Label
  group: string | null
  truncated: boolean
  visible_reviews: number
  total_reviews: number | null
  badges: Badge[]
}

export interface GroupMetrics {
  size: number
  density: number
  core_places: number
  far_areas: string[]
  far_area_count: number
  span_km: number
  type_groups: string[]
  type_diversity: number
  episodes: number | null
  timing_known: boolean
  concentration: number
  core_five_star_share: number | null
  co_timing_ratio: number | null
  member_signal_share: number
}

export interface Group {
  group_id: string
  members: string[]
  pruned: string[]
  edges: [string, string][]
  metrics: GroupMetrics
  trip: {
    trip_like_shape: boolean
    indicators: { one_episode: boolean; low_concentration: boolean; varied_ratings: boolean }
    indicators_met: number
    status: string
  }
  verdict: Verdict
  confidence: number | null
  confidence_parts: { part: string; value: number | null; weight: number; used: boolean }[]
  core_places: string[]
}

export interface ClientRow {
  place_key: string
  title: string | null
  area: string | null
  type: string | null
  type_group: string
  lat: number | null
  lng: number | null
  distance_km: number | null
  core: boolean
  members: string[]
  member_count: number
  date_from: string | null
  date_to: string | null
  avg_rating: number | null
}

export interface ReviewRow {
  review_id: string
  contributor_id: string | null
  display_name?: string
  rating: number | null
  date: string | null
  day: string | null
  label: Label
  badges: string[]
  text: string | null
  text_included?: boolean
  text_length: number | null
  script: string | null
  cluster: string | null
  stock_phrase: boolean
  short: boolean
  reviewer_reviews: number | null
  local_guide: boolean | null
}

export interface Burst {
  start: string
  end: string
  direction: 'positive' | 'negative'
  count: number
  matching: number
  p_value: number
  review_ids: string[]
}

export interface PlaceInfo {
  title: string | null
  area: string | null
  type: string | null
  type_group: string
  lat: number | null
  lng: number | null
  surprise: number
}

export interface GraphEdge {
  source: string
  target: string
  weight: number
  shared: { place_key: string; surprise: number; coincidence: number; popular: boolean }[]
}

export interface Report {
  algorithm_version: string
  pseudonymized?: boolean
  place: {
    place_key: string
    title: string | null
    type: string | null
    type_group: string
    area: string | null
    lat: number | null
    lng: number | null
    rating: number | null
    total_reviews: number | null
  }
  sample: {
    examined: number
    first: string | null
    last: string | null
    expanded: number
    histories_ok: number
    baseline: string[]
    not_checked_high_priority: number
  }
  warnings: string[]
  level: { level: Level; reasons: string[] }
  ratings: {
    examined: number
    sample_mean: number | null
    without_ring: number | null
    without_ring_and_suspicious: number | null
    ring_reviews: number
    overall: null | {
      displayed: number
      total_as_displayed: number
      low: number
      high: number
      no_visible_change: boolean
    }
  }
  signals: {
    T1: {
      skipped: boolean
      reason: string | null
      span_days: number
      n_dated: number
      baseline_per_window: number | null
      baseline_per_week: number | null
      bursts: Burst[]
    }
    T2: Record<string, number>
    T3: {
      thin_max_reviews: number
      five_star: { reviews: number; known: number; unknown: number; thin: number; thin_share: number | null }
      low_star: { reviews: number; known: number; unknown: number; thin: number; thin_share: number | null }
    }
    T4: { clusters: Record<string, string[]>; stock_phrase_clusters: string[] }
    T5: { young: boolean; total_reviews: number | null; sample_span_days: number }
  }
  reviewers: ReviewerRow[]
  graph: { nodes: { id: string; label: Label; display_name?: string }[]; edges: GraphEdge[] }
  groups: Group[]
  reviews: ReviewRow[]
  label_counts: Record<Label, number>
  client_lists: Record<string, ClientRow[]>
  places: Record<string, PlaceInfo>
  evidence: { kind: string; group?: string; text: string; visual: string }[]
  caveats: string[]
  notes: string[]
  names?: Record<string, string>
  analysis?: {
    id: string
    mode: string
    params: Record<string, unknown>
    searches_used: number
    started_at: string | null
    finished_at: string | null
    early_stop: { reason: string; searches_saved: number } | null
    missing: Record<string, number>
    coords_source?: string | null
  }
  budget?: { month_remaining: number; hour_remaining: number }
  ai_summary?: AiSummary
}

export interface AiSummary {
  model: string
  prompt_version: string
  paragraphs: string[]
  source: 'llm' | 'template'
}

export interface AnalysisDetail {
  id: string
  status: string
  stage: string | null
  error: string | null
  searches_used: number
  started_at?: string | null
  finished_at?: string | null
  input: string | null
  paused: { reason: string; resume_at: string | null } | null
  candidates: Candidate[]
  missing: Record<string, number>
  synthetic?: boolean
  report: Report | null
}

export interface Settings {
  mode: Mode
  presentation_mode: boolean
  paraphrase_signal: boolean
  monthly_cap: number
  hourly_cap: number
  per_analysis_cap: number
  serpapi_key_set: boolean
  deepseek_key_set: boolean
}
