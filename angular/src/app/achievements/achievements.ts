import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

import { AchievementsService } from './achievements-service';
import { AuthService } from '../auth/auth-service';
import { ShowOnlyMeStore } from '../shared/show-only-me-store';
import { AchievementEarner } from '../interfaces/achievement';

@Component({
  selector: 'app-achievements',
  standalone: false,
  templateUrl: './achievements.html',
  styleUrl: './achievements.css',
})
export class Achievements implements OnInit {
  private achievementsService = inject(AchievementsService)
  private authService = inject(AuthService)
  private route = inject(ActivatedRoute)
  private onlyMeStore = inject(ShowOnlyMeStore)

  // Read directly from AchievementsService's cache (not a local copy) so the last-known
  // list survives this component being destroyed and recreated on route navigation.
  achievements = this.achievementsService.achievements
  isLoading = signal(this.achievements().length === 0)
  searchQuery = signal('')

  // "Show only me" is on by default. State lives in a shared store so it persists while
  // navigating between badges/achievements/stats, and resets on a full reload. A
  // ?showOnlyMe=true|false query param (read in ngOnInit) still overrides it on load.
  showOnlyMe = this.onlyMeStore.value
  canFilterToMe = computed(() => this.authService.isAuthenticated() && this.authService.claimedPlayerId() != null)
  onlyMe = computed(() => this.showOnlyMe() && this.canFilterToMe())

  filteredAchievements = computed(() => {
    const query = this.searchQuery().trim().toLowerCase()
    let achievements = this.achievements()
    if (this.onlyMe()) {
      const me = this.authService.claimedPlayerId()
      // Keep only achievements I've earned, and show just my chip on each.
      achievements = achievements
        .map(achievement => ({ ...achievement, earners: achievement.earners.filter(earner => earner.player_id === me) }))
        .filter(achievement => achievement.earners.length > 0)
    }
    if (query) {
      achievements = achievements.filter(achievement =>
        achievement.title.toLowerCase().includes(query) ||
        achievement.description.toLowerCase().includes(query) ||
        achievement.earners.some(earner => earner.player_name.toLowerCase().includes(query))
      )
    }
    // Display order only — the backend registry order (ACHIEVEMENT_DEFS in api/main.py) is left as-is.
    return [...achievements].sort((a, b) => a.title.localeCompare(b.title))
  })

  ngOnInit() {
    const param = this.route.snapshot.queryParamMap.get('showOnlyMe')
    if (param === 'false') this.onlyMeStore.set(false)
    else if (param === 'true') this.onlyMeStore.set(true)

    this.achievementsService.getAchievements().subscribe({
      next: achievements => {
        this.achievementsService.setAchievements(achievements)
        this.isLoading.set(false)
      },
      error: () => this.isLoading.set(false),
    })
  }

  toggleOnlyMe(value: boolean) {
    this.onlyMeStore.set(value)
  }

  emptyMessage(): string {
    if (this.onlyMe()) return 'You haven’t earned any achievements yet.'
    if (this.searchQuery().trim()) return 'No achievements match your search.'
    return 'No achievements yet.'
  }

  initials(earner: AchievementEarner): string {
    if (earner.scoreboard_initials) return earner.scoreboard_initials
    return earner.player_name?.slice(0, 2).toUpperCase() ?? '?'
  }

  earnedDate(earner: AchievementEarner): string {
    // earned_at is timestamptz (offset included) — no normalizeDatetime needed here.
    return new Date(earner.earned_at).toLocaleDateString()
  }
}
