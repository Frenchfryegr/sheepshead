export interface AuthSession {
    access_token: string
    refresh_token: string
    expires_at: number
    username: string
    claimed_player_id: number | null
    claimed_player_name: string | null
}

export interface RefreshedTokens {
    access_token: string
    refresh_token: string
    expires_at: number
}

export interface AccountInfo {
    username: string
    claimed_player_id: number | null
    claimed_player_name: string | null
}
