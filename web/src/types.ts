// Shapes of the backend's JSON. Kept in one place so the views stay honest about what they read.

export type Level = 'High' | 'Elevated' | 'Low' | 'Not enough history'
export type Label = 'ring' | 'possible_ring_trip' | 'suspicious' | 'single_use_burst' | 'group_trip' | 'no_flags' | 'not_checked'
export type Verdict = 'ring' | 'possible_ring' | 'possible_ring_trip' | 'ruled_out_trip' | 'social_circle' | 'none'

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
  kept_mean?: number | null
  kept_count?: number | null
  examined?: number | null
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
  core_min_members?: number
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
  core_travel_share: number
  home_area: string | null
  home_member_share: number
  core_near_home_share: number
  travel_party_share: number
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
    positive_evidence?: { shared_home: boolean; travel_party: boolean }
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
  generated_marker?: string | null
  /** The text around a chatbot or placeholder phrase (scrubbed and shortened when pseudonymized). */
  excerpt?: string | null
  /** Every warning sign that applies, in sieve order (older reports don't have them). */
  signs?: SignKey[]
  /** An AI model's opinion of the text, with the phrases it quotes; null when the text wasn't judged. */
  ai?: { verdict: 'ai_style' | 'human_style' | 'unclear'; cues: string[] } | null
}

export type SignKey =
  | 'chatbot_text'
  | 'copied_text'
  | 'first_time_burst'
  | 'linked_group'
  | 'ai_style'
  | 'review_spree'
  | 'first_time_account'

export interface SieveSign {
  name: string
  short: string
  strength: 'strong' | 'opinion' | 'context'
  explain: string
  count: number
  mean: number | null
  set_aside_by_default: boolean
}

export interface AiCoverage {
  min_words: number
  eligible: number
  judged: number
  too_short: number
  no_text: number
  ai_style: number
  human_style: number
  unclear: number
  model: string | null
}

/** Per-review warning signs, strongest first, and what's left once the default ones are set aside. */
export interface Sieve {
  order: SignKey[]
  set_aside_by_default: SignKey[]
  signs: Record<SignKey, SieveSign>
  examined: number
  kept: { count: number; mean: number | null }
  no_signs: { count: number; mean: number | null }
  all: { count: number; mean: number | null }
  ai: AiCoverage
}

export interface FirstTimeSkew {
  available: boolean
  five_star: number
  five_star_first_time?: number
  other: number
  other_first_time?: number
  ratio?: number
  flagged?: boolean
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

export interface SingleUseBurst {
  start: string
  end: string
  direction: 'positive' | 'negative'
  count: number
  single_use: number
  share: number
  flagged: boolean
  review_ids: string[]
}

export type RatingGap =
  | { available: false }
  | {
      available: true
      displayed: number
      total: number
      recent_mean: number
      recent_count: number
      older_count: number
      older_implied_mean: number
      gap: number
      flagged: boolean
    }

export interface GeneratedHit {
  review_id: string
  rating: number | null
  day: string | null
  marker: string
  excerpt?: string | null
  reviewer_reviews: number | null
}

export type TopRated =
  | { available: false }
  | {
      available: true
      count: number
      window_months: number
      window_count: number
      window_start: string
      window_end: string
      window_share: number
      single_use_share: number
      no_photo_share: number
      generated: GeneratedHit[]
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

/** One review from a checked reviewer's public history. `day` is the middle of its approximate date range. */
export interface HistoryItem {
  day: string | null
  rating: number | null
  place_key: string | null
  this: boolean
  area: string | null
  type_group: string
  lat: number | null
  lng: number | null
  km: number | null
}

export interface History {
  total_reviews: number | null
  visible: number
  home_area: string | null
  items: HistoryItem[]
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
    single_use_burst_reviews?: number
    sample_mean: number | null
    kept_mean?: number | null
    kept_count?: number
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
    T6?: { single_use_bursts: SingleUseBurst[] }
    T7?: RatingGap
    T8?: TopRated
    T9?: FirstTimeSkew
  }
  sieve?: Sieve
  reviewers: ReviewerRow[]
  /** Visible histories of the checked reviewers, by contributor id (older reports don't have them). */
  histories?: Record<string, History>
  graph: { nodes: { id: string; label: Label; display_name?: string }[]; edges: GraphEdge[] }
  groups: Group[]
  reviews: ReviewRow[]
  label_counts: Record<Label, number>
  client_lists: Record<string, ClientRow[]>
  places: Record<string, PlaceInfo>
  evidence: Evidence[]
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
  dates_shifted?: boolean
  calibration?: { relative: string | null; true_date: string; estimated_from: string; estimated_to: string | null; inside: boolean }[]
  ai_summary?: AiSummary
}

export interface Evidence {
  kind: string
  group?: string
  text: string
  visual: string
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
