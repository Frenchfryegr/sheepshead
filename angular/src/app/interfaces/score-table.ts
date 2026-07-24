import { Player } from './player'

export interface ScoreTableRow {
    round_number: number
    totals: Map<number, number>
    pickerId: number | null
    partnerId: number | null
    dealerId: number | null
    leasterWinnerId: number | null
}

export interface ScoreTable {
    players: Player[]
    initials: Map<number, string>
    rows: ScoreTableRow[]
    winnerIds: Set<number>
}

export const EMPTY_SCORE_TABLE: ScoreTable = {
    players: [],
    initials: new Map(),
    rows: [],
    winnerIds: new Set(),
}
