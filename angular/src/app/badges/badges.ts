import { Component, OnInit, computed, inject, signal } from '@angular/core';

import { BadgesService } from './badges-service';
import { Badge } from '../interfaces/badge';

@Component({
  selector: 'app-badges',
  standalone: false,
  templateUrl: './badges.html',
  styleUrl: './badges.css',
})
export class Badges implements OnInit {
  private badgesService = inject(BadgesService)

  // Read directly from BadgesService's cache (not a local copy) so the last-known list
  // survives this component being destroyed and recreated on route navigation.
  badges = this.badgesService.badges
  isLoading = signal(this.badges().length === 0)
  searchQuery = signal('')

  filteredBadges = computed(() => {
    const query = this.searchQuery().trim().toLowerCase()
    const badges = query
      ? this.badges().filter(badge =>
          badge.title.toLowerCase().includes(query) ||
          badge.description.toLowerCase().includes(query) ||
          (badge.holder_player_name?.toLowerCase().includes(query) ?? false)
        )
      : this.badges()
    // Display order only — the backend registry order (BADGE_DEFS in api/main.py) is left as-is.
    return [...badges].sort((a, b) => a.title.localeCompare(b.title))
  })

  ngOnInit() {
    this.badgesService.getBadges().subscribe({
      next: badges => {
        this.badgesService.setBadges(badges)
        this.isLoading.set(false)
      },
      error: () => this.isLoading.set(false),
    })
  }

  initials(badge: Badge): string {
    if (badge.holder_scoreboard_initials) return badge.holder_scoreboard_initials
    return badge.holder_player_name?.slice(0, 2).toUpperCase() ?? '?'
  }
}
