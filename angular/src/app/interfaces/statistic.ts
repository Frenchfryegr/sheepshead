export type StatScope = 'overall' | 'three_hand' | 'five_hand'

export interface StatValue {
    value: number | null
    display_value: string | null
    sample_size: number
    // Ratio stats only: the numerator (e.g. wins), so percentages can show a "(num/den)"
    // fraction. Null for count stats.
    numerator: number | null
}

export interface StatLeaderboardEntry {
    player_id: number
    player_name: string
    scoreboard_initials: string | null
    scoreboard_color: string | null
    scoreboard_avatar_url: string | null
    value: number
    display_value: string
    sample_size: number
    numerator: number | null
    rank: number
}

export interface Statistic {
    stat_key: string
    title: string
    description: string
    min_sample: number
    leaderboards: Record<StatScope, StatLeaderboardEntry[]>
}

export interface PlayerStatistic {
    stat_key: string
    title: string
    description: string
    overall: StatValue
    three_hand: StatValue
    five_hand: StatValue
}
