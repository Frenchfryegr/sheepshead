import { inject, Injectable } from '@angular/core';
import { HttpBackend, HttpClient, HttpEvent, HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
import { catchError, finalize, Observable, share, switchMap, tap, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { RefreshedTokens } from '../interfaces/auth';
import { TokenStore } from './token-store';

const NO_RETRY_PATHS = ['/auth/login', '/auth/signup', '/auth/refresh'];

@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  private tokenStore = inject(TokenStore)
  // HttpClient built from HttpBackend directly bypasses the interceptor chain — required here
  // since this interceptor is itself part of that chain (see TokenStore's comment for why it
  // can't just call AuthService.refresh(), which uses the normal, intercepted HttpClient).
  private rawHttp = new HttpClient(inject(HttpBackend))
  // Shared across concurrent 401s so simultaneous requests don't each spend the same (soon
  // to be rotated) refresh token — a race that fails under refresh_token_reuse_interval.
  private refreshInFlight: Observable<RefreshedTokens> | null = null

  intercept(req: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    const token = this.tokenStore.accessToken()
    const authedReq = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req
    const skipRetry = NO_RETRY_PATHS.some(path => req.url.includes(path))

    return next.handle(authedReq).pipe(
      catchError(error => {
        if (error?.status === 401 && token && !skipRetry) {
          return this.refreshTokens().pipe(
            switchMap(tokens => {
              const retryReq = req.clone({ setHeaders: { Authorization: `Bearer ${tokens.access_token}` } })
              return next.handle(retryReq)
            }),
            catchError(refreshError => {
              this.tokenStore.clear()
              return throwError(() => refreshError)
            })
          )
        }
        return throwError(() => error)
      })
    )
  }

  private refreshTokens(): Observable<RefreshedTokens> {
    if (this.refreshInFlight) {
      return this.refreshInFlight
    }

    const refreshToken = this.tokenStore.refreshToken()
    if (!refreshToken) {
      this.tokenStore.clear()
      return throwError(() => new Error('No refresh token available'))
    }

    this.refreshInFlight = this.rawHttp.post<RefreshedTokens>(`${environment.apiUrl}/${environment.auth}/refresh`, {
      refresh_token: refreshToken
    }).pipe(
      tap(tokens => this.tokenStore.persistTokens(tokens.access_token, tokens.refresh_token, tokens.expires_at)),
      finalize(() => { this.refreshInFlight = null }),
      share()
    )
    return this.refreshInFlight
  }
}
