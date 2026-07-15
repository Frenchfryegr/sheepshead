import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, finalize, Observable, switchMap, tap, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { AccountInfo, AuthSession, RefreshedTokens } from '../interfaces/auth';
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
  claimedPlayerId = this.tokenStore.claimedPlayerId
  claimedPlayerName = this.tokenStore.claimedPlayerName
  isAuthenticated = this.tokenStore.isAuthenticated

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
      tap(info => this.tokenStore.setAccountInfo(info.username, info.claimed_player_id, info.claimed_player_name))
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
    this.tokenStore.setAccountInfo(session.username, session.claimed_player_id, session.claimed_player_name)
  }
}
