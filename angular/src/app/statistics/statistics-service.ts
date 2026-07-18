import { inject, Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Statistic, PlayerStatistic } from '../interfaces/statistic';

@Injectable({
  providedIn: 'root',
})
export class StatisticsService {
  private http = inject(HttpClient)

  // Held here (not in the Statistics/Profile components) so the last-known list survives
  // those components being destroyed and recreated on route navigation.
  private statisticsSignal = signal<Statistic[]>([])
  statistics = this.statisticsSignal.asReadonly()

  setStatistics(statistics: Statistic[]): void {
    this.statisticsSignal.set(statistics)
  }

  // Per-player cache so the profile's statistics section survives that component being
  // destroyed and recreated on route navigation (mirrors the list cache above).
  private playerStatisticsCache = new Map<number, PlayerStatistic[]>()

  cachedPlayerStatistics(playerId: number | null | undefined): PlayerStatistic[] {
    if (playerId == null) return []
    return this.playerStatisticsCache.get(playerId) ?? []
  }

  setPlayerStatistics(playerId: number, statistics: PlayerStatistic[]): void {
    this.playerStatisticsCache.set(playerId, statistics)
  }

  getStatistics(): Observable<Statistic[]> {
    return this.http.get<Statistic[]>(`${environment.apiUrl}/${environment.statistics}`)
  }

  getPlayerStatistics(playerId: number): Observable<PlayerStatistic[]> {
    return this.http.get<PlayerStatistic[]>(`${environment.apiUrl}/${environment.statistics}/players/${playerId}`)
  }
}
