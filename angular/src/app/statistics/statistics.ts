import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

import { StatisticsService } from './statistics-service';
import { AuthService } from '../auth/auth-service';
import { ShowOnlyMeStore } from '../shared/show-only-me-store';
import { Statistic, StatLeaderboardEntry, StatScope } from '../interfaces/statistic';

@Component({
  selector: 'app-statistics',
  standalone: false,
  templateUrl: './statistics.html',
  styleUrl: './statistics.css',
})
export class Statistics implements OnInit {
  private statisticsService = inject(StatisticsService)
  private authService = inject(AuthService)
  private route = inject(ActivatedRoute)
  private onlyMeStore = inject(ShowOnlyMeStore)

  // Read directly from StatisticsService's cache (not a local copy) so the last-known
  // list survives this component being destroyed and recreated on route navigation.
  statistics = this.statisticsService.statistics
  isLoading = signal(this.statistics().length === 0)
  // No search box (7 stats) and no alphabetical sort — statistics render in registry order.
  selectedScope = signal<StatScope>('overall')

  // "Show only me" is on by default. State lives in a shared store so it persists while
  // navigating between badges/achievements/stats, and resets on a full reload. A
  // ?showOnlyMe=true|false query param (read in ngOnInit) still overrides it on load.
  showOnlyMe = this.onlyMeStore.value
  canFilterToMe = computed(() => this.authService.isAuthenticated() && this.authService.claimedPlayerId() != null)
  onlyMe = computed(() => this.showOnlyMe() && this.canFilterToMe())

  // In "only me" mode, keep only stats where I have a leaderboard entry in the selected scope.
  visibleStatistics = computed(() => {
    if (!this.onlyMe()) return this.statistics()
    const me = this.authService.claimedPlayerId()
    const scope = this.selectedScope()
    return this.statistics().filter(stat => (stat.leaderboards[scope] ?? []).some(entry => entry.player_id === me))
  })

  ngOnInit() {
    const param = this.route.snapshot.queryParamMap.get('showOnlyMe')
    if (param === 'false') this.onlyMeStore.set(false)
    else if (param === 'true') this.onlyMeStore.set(true)

    this.statisticsService.getStatistics().subscribe({
      next: statistics => {
        this.statisticsService.setStatistics(statistics)
        this.isLoading.set(false)
      },
      error: () => this.isLoading.set(false),
    })
  }

  toggleOnlyMe(value: boolean) {
    this.onlyMeStore.set(value)
  }

  emptyMessage(): string {
    if (this.onlyMe()) return 'You don’t have any qualifying statistics yet.'
    return 'No statistics yet.'
  }

  entries(stat: Statistic): StatLeaderboardEntry[] {
    const all = stat.leaderboards[this.selectedScope()] ?? []
    if (this.onlyMe()) {
      const me = this.authService.claimedPlayerId()
      return all.filter(entry => entry.player_id === me)
    }
    return all
  }

  initials(entry: StatLeaderboardEntry): string {
    if (entry.scoreboard_initials) return entry.scoreboard_initials
    return entry.player_name?.slice(0, 2).toUpperCase() ?? '?'
  }

  // Percentage stats show the full "num/den" fraction; count stats show just the sample.
  detail(entry: StatLeaderboardEntry): string {
    if (entry.numerator != null) return `${entry.numerator}/${entry.sample_size}`
    return `${entry.sample_size}`
  }
}
