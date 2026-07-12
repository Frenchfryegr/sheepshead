import { Round } from "./round"

export interface Game {
    game_id: number
    num_players: number
    Rounds: Round[]
}
