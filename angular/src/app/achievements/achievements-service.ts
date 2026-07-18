import { inject, Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Achievement, PlayerAchievement } from '../interfaces/achievement';

@Injectable({
  providedIn: 'root',
})
export class AchievementsService {
  private http = inject(HttpClient)

  // Held here (not in the Achievements/Profile components) so the last-known list survives
  // those components being destroyed and recreated on route navigation.
  private achievementsSignal = signal<Achievement[]>([])
  achievements = this.achievementsSignal.asReadonly()

  setAchievements(achievements: Achievement[]): void {
    this.achievementsSignal.set(achievements)
  }

  // Per-player cache so the profile's achievements section survives that component being
  // destroyed and recreated on route navigation (mirrors the list cache above).
  private playerAchievementsCache = new Map<number, PlayerAchievement[]>()

  cachedPlayerAchievements(playerId: number | null | undefined): PlayerAchievement[] {
    if (playerId == null) return []
    return this.playerAchievementsCache.get(playerId) ?? []
  }

  setPlayerAchievements(playerId: number, achievements: PlayerAchievement[]): void {
    this.playerAchievementsCache.set(playerId, achievements)
  }

  getAchievements(): Observable<Achievement[]> {
    return this.http.get<Achievement[]>(`${environment.apiUrl}/${environment.achievements}`)
  }

  getPlayerAchievements(playerId: number): Observable<PlayerAchievement[]> {
    return this.http.get<PlayerAchievement[]>(`${environment.apiUrl}/${environment.achievements}/players/${playerId}`)
  }
}
