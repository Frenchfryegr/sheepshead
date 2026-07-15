export interface RoundRow {
    round_id: number
    game_id: number
    round_number: number
    round_result: RoundResult
    no_schneider: boolean
    no_partner: boolean
    no_trick: boolean
}

export interface Round extends RoundRow {
    PlayerRoundScore: PlayerRoundScore[]
}

export type RoundResult = "Picker Win" | "Picker Loss" | "Leaster"

export type PlayerRole = "Picker" | "Partner" | "Opponent" | "Leaster Winner" | "Leaster Loser" | "Dealer"

export interface PlayerRoundScore {
    player_id: number
    player_role: PlayerRole
    point_delta: number
}
