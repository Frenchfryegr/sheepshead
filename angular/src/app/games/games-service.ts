import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Game, CreateGameRequest, CreateRoundRequest, UpdateRoundRequest } from '../interfaces/game';
import { Round, RoundRow } from '../interfaces/round';
import { Player } from '../interfaces/player';

@Injectable({
  providedIn: 'root',
})
export class GamesService {
  private http = inject(HttpClient)

  getGames(): Observable<Game[]> {
    return this.http.get<Game[]>(`${environment.apiUrl}/${environment.games}`)
  }

  getRoundsForGame(game_id: number): Observable<Round[]> {
    return this.http.get<Round[]>(`${environment.apiUrl}/${environment.rounds}/${game_id}`)
  }

  getPlayers(): Observable<Player[]> {
    return this.http.get<Player[]>(`${environment.apiUrl}/${environment.players}`)
  }

  createPlayer(playerName: string): Observable<Player> {
    return this.http.post<Player>(`${environment.apiUrl}/${environment.players}`, null, {
      params: { player_name: playerName }
    })
  }

  createGame(request: CreateGameRequest): Observable<Game> {
    return this.http.post<Game>(`${environment.apiUrl}/${environment.games}`, request)
  }

  createRound(request: CreateRoundRequest): Observable<RoundRow> {
    return this.http.post<RoundRow>(`${environment.apiUrl}/${environment.rounds}`, request)
  }

  updateRound(roundId: number, request: UpdateRoundRequest): Observable<RoundRow> {
    return this.http.patch<RoundRow>(`${environment.apiUrl}/${environment.rounds}/${roundId}`, request)
  }

  deleteRound(roundId: number): Observable<void> {
    return this.http.delete<void>(`${environment.apiUrl}/${environment.rounds}/${roundId}`)
  }

  completeGame(gameId: number): Observable<Game> {
    return this.http.patch<Game>(`${environment.apiUrl}/${environment.games}/${gameId}/complete`, null)
  }
}
