import { Round } from "./round"
import { Player } from "./player"
import { PlayerRoundScore } from "./round"

export interface Game {
    game_id: number
    num_players: number
    game_datetime: string
    is_completed: boolean
    game_name: string | null
    Rounds: Round[]
    Players_X_Games: { Players: Player }[]
}

export interface CreateGameRequest {
    num_players: number
    player_ids: number[]
}

export interface CreateRoundRequest {
    game_id: number
    round_number: number
    round_result: string
    no_schneider: boolean
    no_partner: boolean
    no_trick: boolean
    player_scores: PlayerRoundScore[]
}

export interface UpdateRoundRequest {
    round_result: string
    no_schneider: boolean
    no_partner: boolean
    no_trick: boolean
    player_scores: PlayerRoundScore[]
}
