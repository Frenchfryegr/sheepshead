import { Component, ElementRef, OnInit, ViewChild, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../auth/auth-service';
import { GamesService } from '../games/games-service';
import { BadgesService } from '../badges/badges-service';
import { ProfileInfo } from '../interfaces/auth';
import { Badge } from '../interfaces/badge';
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
}
