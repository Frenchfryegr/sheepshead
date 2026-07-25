import { Player } from '../interfaces/player'

// Shared player-identity presentation helpers. Used by both the Scoreboard in `games.ts` and
// the Table View ring, so the two surfaces can never drift on initials or colors.

const DEFAULT_SCOREBOARD_COLOR = '#1A1A2E'

export function scoreboardColor(player: Player): string {
    return player.scoreboard_color ?? DEFAULT_SCOREBOARD_COLOR
}

export function scoreboardTextColor(player: Player): '#000000' | '#FFFFFF' {
    const color = scoreboardColor(player)
    const red = parseInt(color.slice(1, 3), 16) / 255
    const green = parseInt(color.slice(3, 5), 16) / 255
    const blue = parseInt(color.slice(5, 7), 16) / 255
    const linear = [red, green, blue].map(channel => (
        channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4)
    ))
    const luminance = (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2])
    return luminance > 0.179 ? '#000000' : '#FFFFFF'
}

export function getBaseInitials(name: string): string {
    const tokens = name.trim().split(/\s+/).filter(Boolean)
    if (tokens.length === 0) return '??'
    if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase()
    return (tokens[0][0] + tokens[tokens.length - 1][0]).toUpperCase()
}

export function getEffectiveInitials(player: Player): string {
    return player.scoreboard_initials ?? getBaseInitials(player.player_name)
}

export function sortPlayersByInitials(players: Player[]): Player[] {
    return [...players].sort((a, b) => {
        const initialsCompare = getEffectiveInitials(a).localeCompare(getEffectiveInitials(b))
        return initialsCompare !== 0 ? initialsCompare : a.player_name.localeCompare(b.player_name)
    })
}

// Disambiguates duplicate initials by suffixing an occurrence number (AB -> AB1, AB2).
export function computePlayerInitials(players: Player[]): Map<number, string> {
    const baseInitials = players.map(p => getEffectiveInitials(p))
    const totalCounts = new Map<string, number>()
    for (const initials of baseInitials) {
        totalCounts.set(initials, (totalCounts.get(initials) ?? 0) + 1)
    }

    const seenCounts = new Map<string, number>()
    const result = new Map<number, string>()
    players.forEach((player, i) => {
        const initials = baseInitials[i]
        if ((totalCounts.get(initials) ?? 0) > 1) {
            const occurrence = (seenCounts.get(initials) ?? 0) + 1
            seenCounts.set(initials, occurrence)
            result.set(player.player_id, `${initials}${occurrence}`)
        } else {
            result.set(player.player_id, initials)
        }
    })
    return result
}
