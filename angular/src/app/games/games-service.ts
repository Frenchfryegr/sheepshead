import { inject, Injectable } from '@angular/core';
import { HttpClient, withFetch } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Game } from '../interfaces/game';
import { Round } from '../interfaces/round';

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
}
