import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { BadgesService } from './badges-service';
import { AuthService } from '../auth/auth-service';
import { Badge } from '../interfaces/badge';

@Component({
  selector: 'app-badges',
  standalone: false,
  templateUrl: './badges.html',
  styleUrl: './badges.css',
})
export class Badges implements OnInit {
  private badgesService = inject(BadgesService)
  private authService = inject(AuthService)
  private route = inject(ActivatedRoute)
  private router = inject(Router)

  // Read directly from BadgesService's cache (not a local copy) so the last-known list
  // survives this component being destroyed and recreated on route navigation.
  badges = this.badgesService.badges
  isLoading = signal(this.badges().length === 0)
  searchQuery = signal('')

  // "Show only me" is on by default; a ?showOnlyMe=false query param (read in ngOnInit,
  // written on toggle) overrides it so a shared big-screen URL survives refresh.
  showOnlyMe = signal(true)
  // The toggle only applies when we actually have a "me" to filter to.
  canFilterToMe = computed(() => this.authService.isAuthenticated() && this.authService.claimedPlayerId() != null)
  onlyMe = computed(() => this.showOnlyMe() && this.canFilterToMe())

  filteredBadges = computed(() => {
    const query = this.searchQuery().trim().toLowerCase()
    let badges = this.badges()
    if (this.onlyMe()) {
      const me = this.authService.claimedPlayerId()
      badges = badges.filter(badge => badge.holder_player_id === me)
    }
    if (query) {
      badges = badges.filter(badge =>
        badge.title.toLowerCase().includes(query) ||
        badge.description.toLowerCase().includes(query) ||
        (badge.holder_player_name?.toLowerCase().includes(query) ?? false)
      )
    }
    // Display order only — the backend registry order (BADGE_DEFS in api/main.py) is left as-is.
    return [...badges].sort((a, b) => a.title.localeCompare(b.title))
  })

  ngOnInit() {
    const param = this.route.snapshot.queryParamMap.get('showOnlyMe')
    if (param === 'false') this.showOnlyMe.set(false)
    else if (param === 'true') this.showOnlyMe.set(true)

    this.badgesService.getBadges().subscribe({
      next: badges => {
        this.badgesService.setBadges(badges)
        this.isLoading.set(false)
      },
      error: () => this.isLoading.set(false),
    })
  }

  toggleOnlyMe(value: boolean) {
    this.showOnlyMe.set(value)
    // Reflect the choice in the URL so a refresh (or a bookmarked big-screen URL) keeps it.
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { showOnlyMe: value },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    })
  }

  emptyMessage(): string {
    if (this.onlyMe()) return 'You don’t hold any badges yet.'
    if (this.searchQuery().trim()) return 'No badges match your search.'
    return 'No badges yet.'
  }

  initials(badge: Badge): string {
    if (badge.holder_scoreboard_initials) return badge.holder_scoreboard_initials
    return badge.holder_player_name?.slice(0, 2).toUpperCase() ?? '?'
  }
}
