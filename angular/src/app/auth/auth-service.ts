import { computed, inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, finalize, Observable, switchMap, tap, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { AccountInfo, AuthSession, ProfileInfo, ProfileUpdate, RefreshedTokens } from '../interfaces/auth';
import { TokenStore } from './token-store';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private http = inject(HttpClient)
  private tokenStore = inject(TokenStore)

  accessToken = this.tokenStore.accessToken
  refreshToken = this.tokenStore.refreshToken
  expiresAt = this.tokenStore.expiresAt
  username = this.tokenStore.username
  contactEmail = this.tokenStore.contactEmail
  avatarUrl = this.tokenStore.avatarUrl
  scoreboardInitials = this.tokenStore.scoreboardInitials
  scoreboardColor = this.tokenStore.scoreboardColor
  showAvatarOnScoreboard = this.tokenStore.showAvatarOnScoreboard
  claimedPlayerId = this.tokenStore.claimedPlayerId
  claimedPlayerName = this.tokenStore.claimedPlayerName
  isAuthenticated = this.tokenStore.isAuthenticated

  // Reconstructed from TokenStore's cached fields (a root singleton) so pages that show
  // profile data can render the last-known values immediately on (re)construction, instead
  // of blanking out while a fresh request is in flight.
  profile = computed<ProfileInfo | null>(() => {
    const username = this.tokenStore.username()
    if (!username) return null
    return {
      username,
      contact_email: this.tokenStore.contactEmail(),
      avatar_url: this.tokenStore.avatarUrl(),
      scoreboard_initials: this.tokenStore.scoreboardInitials(),
      scoreboard_color: this.tokenStore.scoreboardColor(),
      show_avatar_on_scoreboard: this.tokenStore.showAvatarOnScoreboard(),
      claimed_player_id: this.tokenStore.claimedPlayerId(),
      claimed_player_name: this.tokenStore.claimedPlayerName(),
    }
  })

  constructor() {
    if (this.tokenStore.accessToken()) {
      this.refreshMe().subscribe({
        error: () => this.tokenStore.clear()
      })
    }
  }

  signup(username: string, password: string, inviteCode: string, email: string | null = null): Observable<AuthSession> {
    return this.http.post<AuthSession>(`${environment.apiUrl}/${environment.auth}/signup`, {
      username, password, invite_code: inviteCode, email
    }).pipe(
      tap(session => this.applySession(session))
    )
  }

  login(username: string, password: string): Observable<AuthSession> {
    return this.http.post<AuthSession>(`${environment.apiUrl}/${environment.auth}/login`, {
      username, password
    }).pipe(
      tap(session => this.applySession(session))
    )
  }

  logout(): Observable<unknown> {
    return this.http.post(`${environment.apiUrl}/${environment.auth}/logout`, {}).pipe(
      finalize(() => this.tokenStore.clear())
    )
  }

  refresh(): Observable<RefreshedTokens> {
    const refreshToken = this.tokenStore.refreshToken()
    if (!refreshToken) {
      this.tokenStore.clear()
      return throwError(() => new Error('No refresh token available'))
    }
    return this.http.post<RefreshedTokens>(`${environment.apiUrl}/${environment.auth}/refresh`, {
      refresh_token: refreshToken
    }).pipe(
      tap(tokens => this.tokenStore.persistTokens(tokens.access_token, tokens.refresh_token, tokens.expires_at)),
      catchError(error => {
        this.tokenStore.clear()
        return throwError(() => error)
      })
    )
  }

  refreshMe(): Observable<AccountInfo> {
    return this.http.get<AccountInfo>(`${environment.apiUrl}/${environment.auth}/me`).pipe(
      tap(info => this.applyProfile(info))
    )
  }

  getProfile(): Observable<ProfileInfo> {
    return this.http.get<ProfileInfo>(`${environment.apiUrl}/${environment.auth}/profile`).pipe(
      tap(info => this.applyProfile(info))
    )
  }

  updateProfile(update: ProfileUpdate): Observable<ProfileInfo> {
    return this.http.patch<ProfileInfo>(`${environment.apiUrl}/${environment.auth}/profile`, update).pipe(
      tap(info => this.applyProfile(info))
    )
  }

  uploadProfilePicture(file: File): Observable<ProfileInfo> {
    const formData = new FormData()
    formData.append('file', file)
    return this.http.post<ProfileInfo>(`${environment.apiUrl}/${environment.auth}/profile/picture`, formData).pipe(
      tap(info => this.applyProfile(info))
    )
  }

  deleteProfilePicture(): Observable<ProfileInfo> {
    return this.http.delete<ProfileInfo>(`${environment.apiUrl}/${environment.auth}/profile/picture`).pipe(
      tap(info => this.applyProfile(info))
    )
  }

  claimPlayer(playerId: number): Observable<AccountInfo> {
    return this.http.post(`${environment.apiUrl}/${environment.players}/${playerId}/claim`, {}).pipe(
      switchMap(() => this.refreshMe())
    )
  }

  unclaimPlayer(playerId: number): Observable<AccountInfo> {
    return this.http.post(`${environment.apiUrl}/${environment.players}/${playerId}/unclaim`, {}).pipe(
      switchMap(() => this.refreshMe())
    )
  }

  private applySession(session: AuthSession) {
    this.tokenStore.persistTokens(session.access_token, session.refresh_token, session.expires_at)
    this.applyProfile(session)
  }

  private applyProfile(info: ProfileInfo) {
    this.tokenStore.setAccountInfo(info)
  }
}
