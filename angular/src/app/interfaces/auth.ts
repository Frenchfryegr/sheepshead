export interface ProfileInfo {
    username: string
    contact_email: string | null
    avatar_url: string | null
    scoreboard_initials: string | null
    scoreboard_color: string | null
    show_avatar_on_scoreboard: boolean
    claimed_player_id: number | null
    claimed_player_name: string | null
}

export interface ProfileUpdate {
    username?: string
    contact_email?: string | null
    scoreboard_initials?: string | null
    scoreboard_color?: string | null
    show_avatar_on_scoreboard?: boolean
}

export interface AuthSession extends ProfileInfo {
    access_token: string
    refresh_token: string
    expires_at: number
}

export interface RefreshedTokens {
    access_token: string
    refresh_token: string
    expires_at: number
}

export type AccountInfo = ProfileInfo
