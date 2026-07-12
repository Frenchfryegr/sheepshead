export interface Round {
    round_id: number,
    game_id: number, 
    round_number: number,
    round_result: RoundResult
}

export type RoundResult  = "Picker Win" | "Picker Loss" | "Leaster"
