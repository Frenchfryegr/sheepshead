import { computed, Injectable, PLATFORM_ID, inject, signal } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

import { ProfileInfo } from '../interfaces/auth';

const STORAGE_KEY = 'sheepshead_auth';

interface StoredTokens {
  accessToken: string
  refreshToken: string
  expiresAt: number
}

// Deliberately has no HttpClient dependency. AuthInterceptor reads/writes tokens through
// this service instead of AuthService, because HttpClient itself depends on HTTP_INTERCEPTORS
// (to build its interceptor chain) — an interceptor that injects HttpClient (directly, or
// transitively via a service like AuthService) creates a circular dependency.
@Injectable({
  providedIn: 'root',
})
export class TokenStore {
  private isBrowser = isPlatformBrowser(inject(PLATFORM_ID))

  accessToken = signal<string | null>(null)
  refreshToken = signal<string | null>(null)
  expiresAt = signal<number | null>(null)
  username = signal<string | null>(null)
  contactEmail = signal<string | null>(null)
  avatarUrl = signal<string | null>(null)
  scoreboardInitials = signal<string | null>(null)
  scoreboardColor = signal<string | null>(null)
  showAvatarOnScoreboard = signal(false)
  claimedPlayerId = signal<number | null>(null)
  claimedPlayerName = signal<string | null>(null)

  isAuthenticated = computed(() => !!this.accessToken())

  constructor() {
    if (this.isBrowser) {
      this.loadFromStorage()
      window.addEventListener('storage', this.onStorageEvent)
    }
  }

  // Keeps tabs in sync: refresh-token rotation in one tab invalidates the token other open
  // tabs are still holding, so without this they'd fail their next refresh and get logged out.
  private onStorageEvent = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return
    if (event.newValue) {
      this.loadFromStorage()
    } else {
      this.clear()
    }
  }

  persistTokens(accessToken: string, refreshToken: string, expiresAt: number) {
    this.accessToken.set(accessToken)
    this.refreshToken.set(refreshToken)
    this.expiresAt.set(expiresAt)
    if (this.isBrowser) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken, refreshToken, expiresAt }))
    }
  }

  setAccountInfo(info: ProfileInfo) {
    this.username.set(info.username)
    this.contactEmail.set(info.contact_email)
    this.avatarUrl.set(info.avatar_url)
    this.scoreboardInitials.set(info.scoreboard_initials)
    this.scoreboardColor.set(info.scoreboard_color)
    this.showAvatarOnScoreboard.set(info.show_avatar_on_scoreboard)
    this.claimedPlayerId.set(info.claimed_player_id)
    this.claimedPlayerName.set(info.claimed_player_name)
  }

  clear() {
    this.accessToken.set(null)
    this.refreshToken.set(null)
    this.expiresAt.set(null)
    this.username.set(null)
    this.contactEmail.set(null)
    this.avatarUrl.set(null)
    this.scoreboardInitials.set(null)
    this.scoreboardColor.set(null)
    this.showAvatarOnScoreboard.set(false)
    this.claimedPlayerId.set(null)
    this.claimedPlayerName.set(null)
    if (this.isBrowser) {
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  private loadFromStorage() {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    try {
      const stored: StoredTokens = JSON.parse(raw)
      this.accessToken.set(stored.accessToken)
      this.refreshToken.set(stored.refreshToken)
      this.expiresAt.set(stored.expiresAt)
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  }
}
