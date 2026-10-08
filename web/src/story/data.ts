// The real findings the home page's story is told with, generated from three stored analyses by
// `uv run python -m reviewring.story_data` (numbers only: no names, ids, review texts or calendar dates).

import raw from './data.json'

export interface SpreeItem { area: string | null; lat: number | null; lng: number | null; rating: number | null; type_group: string; this: boolean; in_window: boolean; day: number | null }

export interface StoryData {
  hotel: {
    type: string; area: string; shown: number; total_approx: number; ratings: number[]; days: number[]; mean: number; older_mean: number
    top: { count: number; window: number; months: number; first_time_share: number }
    chatbot: string
    ai: { judged: number; ai_style: number; ratings: number[] }
    spree: { places: number; areas: string[]; visible: number; items: SpreeItem[] }
  }
  mover: {
    type: string; area: string; shown: number; total_approx: number; reviews: { rating: number; signs: string[] }[]; days: number[]
    mean: number; kept_mean: number; kept: number
    burst: { count: number; first_time: number; days: number }
    ai: { judged: number; ai_style: number; first_time: number; ratings: number[] }
    first_time_accounts: number
  }
  clean: { area: string; level: string; mean: number; strong_signs: number; first_time_accounts: number; waves: number; histories: number; voice_compared: number; voice_same: number }
  scripted: {
    area: string; shown: number; total_approx: number; mean: number; kept: number; kept_mean: number
    keyword_accounts: number; with_text: number; phrases: string[]; signs: Record<string, number>
    voice: { compared: number; different: number; here: string; elsewhere: string }
  }
  research: { label: string; city: string; with_text: number; keyword_accounts: number }[]
}

export const STORY = raw as unknown as StoryData
