import { Component, OnInit, computed, inject, signal } from '@angular/core';

import { AchievementsService } from './achievements-service';
import { AchievementEarner } from '../interfaces/achievement';

@Component({
  selector: 'app-achievements',
  standalone: false,
  templateUrl: './achievements.html',
  styleUrl: './achievements.css',
})
export class Achievements implements OnInit {
  private achievementsService = inject(AchievementsService)

  // Read directly from AchievementsService's cache (not a local copy) so the last-known
  // list survives this component being destroyed and recreated on route navigation.
  achievements = this.achievementsService.achievements
  isLoading = signal(this.achievements().length === 0)
  searchQuery = signal('')

  filteredAchievements = computed(() => {
    const query = this.searchQuery().trim().toLowerCase()
    const achievements = query
      ? this.achievements().filter(achievement =>
          achievement.title.toLowerCase().includes(query) ||
          achievement.description.toLowerCase().includes(query) ||
          achievement.earners.some(earner => earner.player_name.toLowerCase().includes(query))
        )
      : this.achievements()
    // Display order only — the backend registry order (ACHIEVEMENT_DEFS in api/main.py) is left as-is.
    return [...achievements].sort((a, b) => a.title.localeCompare(b.title))
  })

  ngOnInit() {
    this.achievementsService.getAchievements().subscribe({
      next: achievements => {
        this.achievementsService.setAchievements(achievements)
        this.isLoading.set(false)
      },
      error: () => this.isLoading.set(false),
    })
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
