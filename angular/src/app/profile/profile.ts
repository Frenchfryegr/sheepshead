import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../auth/auth-service';
import { GamesService } from '../games/games-service';
import { BadgesService } from '../badges/badges-service';
import { AchievementsService } from '../achievements/achievements-service';
import { StatisticsService } from '../statistics/statistics-service';
import { ProfileInfo } from '../interfaces/auth';
import { Badge } from '../interfaces/badge';
import { PlayerAchievement, PlayerAchievementTier } from '../interfaces/achievement';
import { PlayerStatistic, StatScope, StatValue } from '../interfaces/statistic';
import { Player } from '../interfaces/player';

const MAX_PROFILE_PICTURE_BYTES = 2 * 1024 * 1024

@Component({
  selector: 'app-profile',
  standalone: false,
  templateUrl: './profile.html',
  styleUrl: './profile.css',
})
export class Profile implements OnInit {
  private authService = inject(AuthService)
  private gamesService = inject(GamesService)
  private badgesService = inject(BadgesService)
  private achievementsService = inject(AchievementsService)
  private statisticsService = inject(StatisticsService)
  private router = inject(Router)

  @ViewChild('ClaimDialog') claimDialog!: ElementRef<HTMLDialogElement>

  // Seeded from AuthService/BadgesService's caches (both root singletons) so this component
  // shows the last-known profile immediately if it's destroyed and recreated on route
  // navigation, instead of blanking out to "Loading profile..." while it refetches.
  profile = signal<ProfileInfo | null>(this.authService.profile())
  username = signal(this.profile()?.username ?? '')
  contactEmail = signal(this.profile()?.contact_email ?? '')
  scoreboardInitials = signal(this.profile()?.scoreboard_initials ?? '')
  scoreboardColor = signal(this.profile()?.scoreboard_color ?? '')
  showAvatarOnScoreboard = signal(this.profile()?.show_avatar_on_scoreboard ?? false)
  errorMessage = signal<string | null>(null)
  successMessage = signal<string | null>(null)
  isLoading = signal(!this.profile())
  isSaving = signal(false)
  isUploading = signal(false)
  isDeletingPicture = signal(false)
  players = signal<Player[]>([])
  claimError = signal<string | null>(null)
  heldBadges = signal<Badge[]>(this.filterHeldBadges(this.badgesService.badges(), this.profile()))
  playerAchievements = signal<PlayerAchievement[]>(
    this.sortAchievements(this.achievementsService.cachedPlayerAchievements(this.profile()?.claimed_player_id))
  )
  // No sorting — statistics preserve API (registry) order, unlike badges/achievements.
  playerStatistics = signal<PlayerStatistic[]>(
    this.statisticsService.cachedPlayerStatistics(this.profile()?.claimed_player_id)
  )
  // Split toggle for the stat tiles, mirroring the public /statistics page.
  selectedStatScope = signal<StatScope>('overall')

  ngOnInit() {
    this.loadProfile()
  }

  loadProfile() {
    // Only show the loading state on a genuinely first load; if we already have cached
    // data (from a prior visit this session), refresh it in the background instead.
    if (!this.profile()) this.isLoading.set(true)
    this.errorMessage.set(null)
    this.authService.getProfile().subscribe({
      next: (profile) => {
        this.applyProfile(profile)
        this.loadHeldBadges(profile)
        this.loadPlayerAchievements(profile)
        this.loadPlayerStatistics(profile)
        this.isLoading.set(false)
      },
      error: (err) => {
        this.isLoading.set(false)
        if (err?.status === 401 || err?.status === 404) {
          this.router.navigate(['/'])
          return
        }
        this.errorMessage.set(err?.error?.detail ?? 'Could not load profile')
      }
    })
  }

  saveProfile() {
    const username = this.username().trim()
    const contactEmail = this.contactEmail().trim()
    const initials = this.scoreboardInitials().trim().toUpperCase()
    const color = this.scoreboardColor().trim().toUpperCase()

    this.errorMessage.set(null)
    this.successMessage.set(null)
    this.isSaving.set(true)
    this.authService.updateProfile({
      username,
      contact_email: contactEmail || null,
      scoreboard_initials: initials || null,
      scoreboard_color: color || null,
      show_avatar_on_scoreboard: this.showAvatarOnScoreboard(),
    }).subscribe({
      next: (profile) => {
        this.applyProfile(profile)
        this.successMessage.set('Profile saved')
        this.isSaving.set(false)
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail ?? 'Could not save profile')
        this.isSaving.set(false)
      }
    })
  }

  onPictureSelected(event: Event) {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file) return

    this.errorMessage.set(null)
    this.successMessage.set(null)
    if (file.size > MAX_PROFILE_PICTURE_BYTES) {
      this.errorMessage.set('Profile picture must be 2 MiB or smaller')
      return
    }

    this.isUploading.set(true)
    this.authService.uploadProfilePicture(file).subscribe({
      next: (profile) => {
        this.applyProfile(profile)
        this.successMessage.set('Profile picture updated')
        this.isUploading.set(false)
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail ?? 'Could not upload profile picture')
        this.isUploading.set(false)
      }
    })
  }

  deletePicture() {
    this.errorMessage.set(null)
    this.successMessage.set(null)
    this.isDeletingPicture.set(true)
    this.authService.deleteProfilePicture().subscribe({
      next: (profile) => {
        this.applyProfile(profile)
        this.successMessage.set('Profile picture deleted')
        this.isDeletingPicture.set(false)
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail ?? 'Could not delete profile picture')
        this.isDeletingPicture.set(false)
      }
    })
  }

  openClaimDialog() {
    this.claimError.set(null)
    this.gamesService.getPlayers().subscribe({
      next: players => {
        this.players.set(players)
        this.claimDialog.nativeElement.showModal()
      },
      error: (err) => this.errorMessage.set(err?.error?.detail ?? 'Could not load players')
    })
  }

  closeClaimDialog() {
    this.claimDialog.nativeElement.close()
  }

  onClaimBackdropClick(event: MouseEvent) {
    if (event.target !== event.currentTarget) return
    this.closeClaimDialog()
  }

  claim(playerId: number) {
    this.claimError.set(null)
    this.authService.claimPlayer(playerId).subscribe({
      next: profile => {
        this.applyProfile(profile)
        this.loadHeldBadges(profile)
        this.loadPlayerAchievements(profile)
        this.loadPlayerStatistics(profile)
      },
      error: (err) => this.claimError.set(err?.error?.detail ?? 'Could not claim player')
    })
  }

  unclaim(playerId: number) {
    this.claimError.set(null)
    this.authService.unclaimPlayer(playerId).subscribe({
      next: profile => {
        this.applyProfile(profile)
        this.loadHeldBadges(profile)
        this.loadPlayerAchievements(profile)
        this.loadPlayerStatistics(profile)
      },
      error: (err) => this.claimError.set(err?.error?.detail ?? 'Could not unclaim player')
    })
  }

  fallbackInitials(): string {
    const source = this.username().trim() || this.profile()?.username || '?'
    const tokens = source.trim().split(/\s+/).filter(Boolean)
    if (tokens.length === 0) return '?'
    if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase()
    return (tokens[0][0] + tokens[tokens.length - 1][0]).toUpperCase()
  }

  private applyProfile(profile: ProfileInfo) {
    this.profile.set(profile)
    this.username.set(profile.username)
    this.contactEmail.set(profile.contact_email ?? '')
    this.scoreboardInitials.set(profile.scoreboard_initials ?? '')
    this.scoreboardColor.set(profile.scoreboard_color ?? '')
    this.showAvatarOnScoreboard.set(profile.show_avatar_on_scoreboard)
  }

  private loadHeldBadges(profile: ProfileInfo) {
    if (profile.claimed_player_id === null) {
      this.heldBadges.set([])
      return
    }
    this.badgesService.getBadges().subscribe({
      next: badges => {
        this.badgesService.setBadges(badges)
        this.heldBadges.set(this.filterHeldBadges(badges, profile))
      },
      error: () => this.heldBadges.set([]),
    })
  }

  private filterHeldBadges(badges: Badge[], profile: ProfileInfo | null): Badge[] {
    if (!profile || profile.claimed_player_id === null) return []
    return badges
      .filter(badge => badge.holder_player_id === profile.claimed_player_id)
      // Display order only — the backend registry order (BADGE_DEFS in api/main.py) is left as-is.
      .sort((a, b) => a.title.localeCompare(b.title))
  }

  private loadPlayerAchievements(profile: ProfileInfo) {
    const playerId = profile.claimed_player_id
    if (playerId === null) {
      this.playerAchievements.set([])
      return
    }
    this.achievementsService.getPlayerAchievements(playerId).subscribe({
      next: achievements => {
        this.achievementsService.setPlayerAchievements(playerId, achievements)
        this.playerAchievements.set(this.sortAchievements(achievements))
      },
      error: () => this.playerAchievements.set([]),
    })
  }

  private sortAchievements(achievements: PlayerAchievement[]): PlayerAchievement[] {
    // Display order only — the backend registry order (ACHIEVEMENT_DEFS in api/main.py) is left as-is.
    return [...achievements].sort((a, b) => a.title.localeCompare(b.title))
  }

  private loadPlayerStatistics(profile: ProfileInfo) {
    const playerId = profile.claimed_player_id
    if (playerId === null) {
      this.playerStatistics.set([])
      return
    }
    this.statisticsService.getPlayerStatistics(playerId).subscribe({
      next: statistics => {
        this.statisticsService.setPlayerStatistics(playerId, statistics)
        // No sorting — preserve API (registry) order (deliberate deviation from badges/achievements).
        this.playerStatistics.set(statistics)
      },
      error: () => this.playerStatistics.set([]),
    })
  }

  // The StatValue for the currently selected scope (overall / three_hand / five_hand).
  selectedStatValue(stat: PlayerStatistic): StatValue {
    return stat[this.selectedStatScope()]
  }

  // Percentage stats show the full "num/den" fraction; count stats show just the sample.
  statDetail(value: StatValue): string {
    if (value.numerator != null) return `${value.numerator}/${value.sample_size}`
    return `${value.sample_size}`
  }

  // A split's percentage with its "(num/den)" fraction, or "—" when there's no sample.
  splitLabel(value: StatValue): string {
    if (value.display_value == null) return '—'
    if (value.numerator != null) return `${value.display_value} (${value.numerator}/${value.sample_size})`
    return value.display_value
  }

  achievementProgress(achievement: PlayerAchievement): number {
    if (!achievement.next_tier || achievement.next_tier.threshold <= 0) return 1
    return Math.min(1, achievement.current_value / achievement.next_tier.threshold)
  }

  tierTooltip(tier: PlayerAchievementTier): string {
    if (tier.earned) {
      const date = tier.earned_at ? new Date(tier.earned_at).toLocaleDateString() : ''
      return date ? `${tier.tier} — earned ${date}` : `${tier.tier} — earned`
    }
    return `${tier.tier} — reach ${tier.display_threshold}`
  }
}
