import { Component, OnInit, inject, signal } from '@angular/core';

import { StatisticsService } from './statistics-service';
import { Statistic, StatLeaderboardEntry, StatScope } from '../interfaces/statistic';

@Component({
  selector: 'app-statistics',
  standalone: false,
  templateUrl: './statistics.html',
  styleUrl: './statistics.css',
})
export class Statistics implements OnInit {
  private statisticsService = inject(StatisticsService)

  // Read directly from StatisticsService's cache (not a local copy) so the last-known
  // list survives this component being destroyed and recreated on route navigation.
  statistics = this.statisticsService.statistics
  isLoading = signal(this.statistics().length === 0)
  // No search box (7 stats) and no alphabetical sort — statistics render in registry order.
  selectedScope = signal<StatScope>('overall')

  ngOnInit() {
    this.statisticsService.getStatistics().subscribe({
      next: statistics => {
        this.statisticsService.setStatistics(statistics)
        this.isLoading.set(false)
      },
      error: () => this.isLoading.set(false),
    })
  }

  entries(stat: Statistic): StatLeaderboardEntry[] {
    return stat.leaderboards[this.selectedScope()] ?? []
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
