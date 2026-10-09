// The real findings the home page's story is told with, generated from three stored analyses by
// `uv run python -m reviewring.story_data` (numbers only: no names, ids, review texts or calendar dates).

import raw from './data.json'

export interface SpreeItem { area: string | null; lat: number | null; lng: number | null; rating: number | null; type_group: string; this: boolean; in_window: boolean; day: number | null }

export type TplKind = 'word' | 'blank' | 'slot' | 'typo'

export interface StoryData {
  hotel: {
    type: string; area: string; shown: number; total_approx: number; ratings: number[]; days: number[]; mean: number; older_mean: number
    top: { count: number; window: number; months: number; first_time_share: number }
    chatbot: string
    spree: { places: number; areas: string[]; visible: number; items: SpreeItem[] }
  }
  mover: {
    type: string; area: string; shown: number; total_approx: number; reviews: { rating: number; signs: string[] }[]; days: number[]
    mean: number; kept_mean: number; kept: number
    burst: { count: number; first_time: number; minutes: number; core: number; core_minutes: number; share: number; usual_every_days: number | null; offsets: number[] }
    first_time_accounts: number
  }
  clean: {
    area: string; level: string; mean: number; strong_signs: number; first_time_accounts: number; waves: number; histories: number
    voice: { lines: { place: string; text: string; here: boolean }[]; reviews: number } | null
  }
  scripted: {
    area: string; shown: number; total_approx: number; mean: number; kept: number; kept_mean: number
    keyword_accounts: number; with_text: number; phrases: string[]; signs: Record<string, number>
    ads: number; ad_phrases: string[]; name_phrases: string[]; kept_named: number; kept_named_mean: number | null
    same_script: { here: [string, TplKind][]; there: [string, TplKind][]; type: string }[]
    copies: {
      count: number; templates: number
      template: null | {
        lines: { words: [string, TplKind][]; copies: number }[]
        typo: { word: string; accounts: number; written: string[] } | null
        accounts: number; first_time: number; five_star: number; months: number
      }
    }
  }
  research: { label: string; city: string; with_text: number; keyword_accounts: number }[]
}

export const STORY = raw as unknown as StoryData
