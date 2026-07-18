export type AchievementTierName = 'bronze' | 'silver' | 'gold'

export interface AchievementTier {
    tier: AchievementTierName
    threshold: number
    display_threshold: string
}

export interface AchievementEarner {
    player_id: number
    player_name: string
    scoreboard_initials: string | null
    scoreboard_color: string | null
    scoreboard_avatar_url: string | null
    tier: AchievementTierName
    earned_at: string
    tiers_earned: Partial<Record<AchievementTierName, string>>
}

export interface Achievement {
    achievement_key: string
    title: string
    description: string
    tiers: AchievementTier[]
    earners: AchievementEarner[]
}

export interface PlayerAchievementTier extends AchievementTier {
    // Sticky: earned comes from the backend's stored rows, never from current_value —
    // a tier stays earned even if later data edits drop current_value below its threshold.
    earned: boolean
    earned_at: string | null
}

export interface PlayerAchievement {
    achievement_key: string
    title: string
    description: string
    current_value: number
    display_value: string
    tiers: PlayerAchievementTier[]
    highest_earned_tier: AchievementTierName | null
    next_tier: PlayerAchievementTier | null
}
