import { HttpClient } from '@angular/common/http'
import { inject, Injectable } from '@angular/core'
import { Observable } from 'rxjs'

import { environment } from '../../environments/environment'
import {
  AbandonOnlineGameResponse,
  CreateOnlineGameRequest,
  OnlineAction,
  OnlineGameSummary,
  OnlineGameView,
  OnlinePlaystyle,
} from '../interfaces/online-game'

@Injectable({ providedIn: 'root' })
export class OnlineGameService {
  private http = inject(HttpClient)
  private readonly url = `${environment.apiUrl}/${environment.onlineGames}`

  listMyGames(): Observable<OnlineGameSummary[]> {
    return this.http.get<OnlineGameSummary[]>(this.url)
  }

  listPlaystyles(): Observable<OnlinePlaystyle[]> {
    return this.http.get<OnlinePlaystyle[]>(`${this.url}/playstyles`)
  }

  createGame(request: CreateOnlineGameRequest): Observable<OnlineGameView> {
    return this.http.post<OnlineGameView>(this.url, request)
  }

  getGame(id: number): Observable<OnlineGameView> {
    return this.http.get<OnlineGameView>(`${this.url}/${id}`)
  }

  sendAction(id: number, version: number, action: OnlineAction): Observable<OnlineGameView> {
    return this.http.post<OnlineGameView>(`${this.url}/${id}/actions`, { version, action })
  }

  abandon(id: number, version: number): Observable<AbandonOnlineGameResponse> {
    return this.http.post<AbandonOnlineGameResponse>(`${this.url}/${id}/abandon`, { version })
  }
}
