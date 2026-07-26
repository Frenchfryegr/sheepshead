export type OnlineCard = string
export type OnlinePhase = 'picking' | 'burying' | 'calling' | 'playing' | 'hand_done' | 'game_over'

export interface OnlineRuleSet {
  num_players: number
  cards_per_player: number
  blind_size: number
  partner_method: string
  leaster_enabled: boolean
  leaster_blind: string
}

export interface OnlineSeatPublic {
  index: number
  name: string
  is_human: boolean
  /** Playstyle key for AI seats, null for the human. Public by design. */
  ai_strategy: string | null
  card_count: number
  trick_count: number
  taken_points: number | null
}

export type OnlineAction =
  | { type: 'pick' }
  | { type: 'pass' }
  | { type: 'bury', cards: OnlineCard[] }
  | { type: 'unbury' }
  | { type: 'call', card: OnlineCard | null }
  | { type: 'call_under', card: OnlineCard, under: OnlineCard }
  | { type: 'play', card: OnlineCard }

export interface OnlineHandResult {
  hand_number: number
  kind: 'picker_win' | 'picker_loss' | 'leaster'
  picker_seat: number | null
  partner_seat: number | null
  called_card: OnlineCard | null
  deltas: number[]
  points: number[]
  buried_points: number
  picker_team_points: number | null
  multiplier: number
  no_schneider: boolean
  no_trick: boolean
  leaster_winner: number | null
}

export interface OnlineEvent {
  type: string
  seat?: number
  /** Null on a card_played event for an under this seat may not see. */
  card?: OnlineCard | null
  /** Set when the played card was the picker's face-down under. */
  under?: boolean
  points?: number
  hand_number?: number
  result?: OnlineHandResult
}

export interface OnlineTrickCard {
  seat: number
  /** Null when this seat may not see the picker's face-down under. */
  card: OnlineCard | null
  /** Public even when `card` is masked — everyone watches a card go down face first. */
  under?: boolean
}

export interface OnlineCompletedTrick {
  winner: number
  plays: OnlineTrickCard[]
}

export interface OnlineGameView {
  online_game_id: number
  status: 'in_progress' | 'completed' | 'abandoned'
  ruleset: OnlineRuleSet
  seat: number
  seats: OnlineSeatPublic[]
  scores: number[]
  hand_number: number
  dealer_seat: number
  hand: OnlineCard[]
  phase: OnlinePhase
  turn_seat: number | null
  passes: number[]
  picker_seat: number | null
  called_card: OnlineCard | null
  partner_revealed: boolean
  partner_seat: number | null
  is_leaster: boolean
  current_trick: OnlineTrickCard[]
  completed_tricks: OnlineCompletedTrick[]
  /** The picker's own under card; null for every other seat. */
  under_card: OnlineCard | null
  /** Whether the picker called under. Public — only its identity is hidden. */
  under_declared: boolean
  legal_actions: OnlineAction[]
  hand_history: OnlineHandResult[]
  events: OnlineEvent[]
  version: number
}

export interface OnlineGameSummary {
  online_game_id: number
  status: 'in_progress' | 'completed' | 'abandoned'
  hand_number: number
  scores: number[]
  seats: Array<{ index: number, name: string, is_human: boolean, ai_strategy: string | null }>
  version: number
  created: string
  updated_at: string
}

export interface OnlinePlaystyle {
  key: string
  name: string
  description: string
}

export interface CreateOnlineGameRequest {
  ruleset_preset?: string
  ai_strategies?: string | string[]
  seat_names?: string[]
}

export interface DeleteOnlineGameResponse {
  online_game_id: number
  deleted: true
}

export interface AbandonOnlineGameResponse {
  online_game_id: number
  status: 'abandoned'
  scores: number[]
  hand_number: number
  version: number
}
