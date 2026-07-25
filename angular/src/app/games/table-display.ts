import { inject, Injectable, PLATFORM_ID } from '@angular/core'
import { isPlatformBrowser } from '@angular/common'

// Paired with the `html.app-dark-canvas` rule in styles.css.
const DARK_CANVAS_CLASS = 'app-dark-canvas'

// Keeps the screen awake and (best-effort) fullscreen while Table View is on — the phone is
// lying flat on the table between rounds, so the default dim/lock behaviour is wrong.
//
// Everything here is a progressive enhancement: unsupported browsers (notably iOS Safari for
// fullscreen on a <dialog>) simply do nothing, and the CSS viewport-fill layout is what
// actually guarantees the display. Never let a rejected promise here break the mode.
@Injectable({ providedIn: 'root' })
export class TableDisplay {
    private platformId = inject(PLATFORM_ID)
    private isBrowser = isPlatformBrowser(this.platformId)
    private wakeLock: WakeLockSentinel | null = null
    private active = false

    // The browser releases the wake lock whenever the tab is backgrounded (e.g. the user takes
    // a call mid-game). Re-acquire it when we come back, as long as Table View is still on.
    private onVisibilityChange = () => {
        if (this.active && document.visibilityState === 'visible') void this.acquireWakeLock()
    }

    // Must be called from inside a user-gesture handler — fullscreen requests are rejected
    // otherwise.
    async enable(element: HTMLElement): Promise<void> {
        if (!this.isBrowser || this.active) return
        this.active = true
        // Match the canvas to the felt, so the iOS home-indicator strip isn't a white band.
        document.documentElement.classList.add(DARK_CANVAS_CLASS)
        document.addEventListener('visibilitychange', this.onVisibilityChange)
        await this.acquireWakeLock()
        try {
            if (!document.fullscreenElement) await element.requestFullscreen?.()
        } catch {
            // Denied or unsupported — the CSS layout still fills the viewport.
        }
    }

    async disable(): Promise<void> {
        if (!this.isBrowser || !this.active) return
        this.active = false
        document.documentElement.classList.remove(DARK_CANVAS_CLASS)
        document.removeEventListener('visibilitychange', this.onVisibilityChange)
        await this.releaseWakeLock()
        try {
            // The user may already have left fullscreen themselves (Esc, system gesture) —
            // calling exitFullscreen() with nothing fullscreened throws.
            if (document.fullscreenElement) await document.exitFullscreen()
        } catch {
            // Nothing actionable.
        }
    }

    private async acquireWakeLock(): Promise<void> {
        if (this.wakeLock) return
        try {
            this.wakeLock = await navigator.wakeLock?.request('screen') ?? null
            // Clear our handle if the browser drops it, so re-acquiring works.
            this.wakeLock?.addEventListener('release', () => { this.wakeLock = null })
        } catch {
            this.wakeLock = null
        }
    }

    private async releaseWakeLock(): Promise<void> {
        try {
            await this.wakeLock?.release()
        } catch {
            // Already released.
        }
        this.wakeLock = null
    }
}
