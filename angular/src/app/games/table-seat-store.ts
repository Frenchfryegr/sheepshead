import { inject, Injectable, PLATFORM_ID } from '@angular/core'
import { isPlatformBrowser } from '@angular/common'
import { Player } from '../interfaces/player'

// Seat order for Table View is a purely local display preference — there is no DB column for
// it. Stored per game id in localStorage. Deliberately has no HttpClient dependency (mirrors
// how TokenStore is factored) and every browser API touch is SSR-guarded.
@Injectable({ providedIn: 'root' })
export class TableSeatStore {
    private platformId = inject(PLATFORM_ID)
    private isBrowser = isPlatformBrowser(this.platformId)

    private key(gameId: number): string {
        return `sheepshead.tableSeats.${gameId}`
    }

    // Returns player ids in seat order. Always reconciled against the live roster, so a stale
    // stored order can never drop a seat or surface a player who left the game.
    order(gameId: number | null, roster: Player[]): number[] {
        return this.reconcile(this.read(gameId), roster)
    }

    save(gameId: number | null, playerIds: number[]): void {
        if (!this.isBrowser || gameId === null) return
        try {
            localStorage.setItem(this.key(gameId), JSON.stringify(playerIds))
        } catch {
            // Private mode / quota — seat order is cosmetic, so failing to persist is fine.
        }
    }

    private read(gameId: number | null): number[] {
        if (!this.isBrowser || gameId === null) return []
        try {
            const raw = localStorage.getItem(this.key(gameId))
            if (!raw) return []
            const parsed = JSON.parse(raw)
            return Array.isArray(parsed) ? parsed.filter((id: unknown) => typeof id === 'number') : []
        } catch {
            return []
        }
    }

    // Drop ids no longer on the roster, drop duplicates, then append roster players the stored
    // order doesn't mention. A stored order that doesn't match the roster degrades to roster
    // order rather than producing a missing or duplicated seat.
    private reconcile(stored: number[], roster: Player[]): number[] {
        const rosterIds = new Set(roster.map(p => p.player_id))
        const seen = new Set<number>()
        const ordered: number[] = []

        for (const id of stored) {
            if (rosterIds.has(id) && !seen.has(id)) {
                ordered.push(id)
                seen.add(id)
            }
        }
        for (const player of roster) {
            if (!seen.has(player.player_id)) ordered.push(player.player_id)
        }
        return ordered
    }
}
