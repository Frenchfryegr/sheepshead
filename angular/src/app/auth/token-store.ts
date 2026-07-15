import { computed, Injectable, PLATFORM_ID, inject, signal } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

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
  claimedPlayerId = signal<number | null>(null)

  isAuthenticated = computed(() => !!this.accessToken())

  constructor() {
    if (this.isBrowser) {
      this.loadFromStorage()
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

  setAccountInfo(username: string, claimedPlayerId: number | null) {
    this.username.set(username)
    this.claimedPlayerId.set(claimedPlayerId)
  }

  clear() {
    this.accessToken.set(null)
    this.refreshToken.set(null)
    this.expiresAt.set(null)
    this.username.set(null)
    this.claimedPlayerId.set(null)
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
