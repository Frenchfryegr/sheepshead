import { AfterViewInit, Component, ElementRef, inject, signal, ViewChild } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../auth-service';
import { GamesService } from '../../games/games-service';
import { Player } from '../../interfaces/player';

type AuthMode = 'login' | 'signup';

@Component({
  selector: 'app-account-bar',
  standalone: false,
  templateUrl: './account-bar.html',
  styleUrl: './account-bar.css',
})
export class AccountBar implements AfterViewInit {
  protected authService = inject(AuthService)
  private gamesService = inject(GamesService)
  private router = inject(Router)
  private savedScrollY = 0

  @ViewChild('AuthDialog') authDialog!: ElementRef<HTMLDialogElement>
  @ViewChild('ClaimDialog') claimDialog!: ElementRef<HTMLDialogElement>

  ngAfterViewInit() {
    this.authDialog.nativeElement.addEventListener('close', () => this.unlockBodyScroll())
    this.claimDialog.nativeElement.addEventListener('close', () => this.unlockBodyScroll())
  }

  mode = signal<AuthMode>('login')
  usernameInput = signal('')
  passwordInput = signal('')
  confirmPasswordInput = signal('')
  inviteCodeInput = signal('')
  emailInput = signal('')
  errorMessage = signal<string | null>(null)
  isSubmitting = signal(false)

  players = signal<Player[]>([])
  claimError = signal<string | null>(null)

  openAuthDialog(mode: AuthMode) {
    this.mode.set(mode)
    this.errorMessage.set(null)
    this.usernameInput.set('')
    this.passwordInput.set('')
    this.confirmPasswordInput.set('')
    this.inviteCodeInput.set('')
    this.emailInput.set('')
    this.showDialogModal(this.authDialog.nativeElement)
  }

  switchMode(mode: AuthMode) {
    this.mode.set(mode)
    this.errorMessage.set(null)
  }

  closeDialog() {
    this.authDialog.nativeElement.close()
  }

  onBackdropClick(event: MouseEvent) {
    if (event.target !== event.currentTarget) return
    this.closeDialog()
  }

  submit() {
    const username = this.usernameInput().trim()
    const password = this.passwordInput()
    if (!username || !password) {
      this.errorMessage.set('Username and password are required')
      return
    }

    if (this.mode() === 'signup') {
      if (password !== this.confirmPasswordInput()) {
        this.errorMessage.set('Passwords do not match')
        return
      }
      const inviteCode = this.inviteCodeInput().trim()
      if (!inviteCode) {
        this.errorMessage.set('Invite code is required')
        return
      }
      const email = this.emailInput().trim() || null
      this.isSubmitting.set(true)
      this.authService.signup(username, password, inviteCode, email).subscribe({
        next: () => {
          this.isSubmitting.set(false)
          this.closeDialog()
        },
        error: (err) => {
          this.isSubmitting.set(false)
          this.errorMessage.set(err?.error?.detail ?? 'Sign up failed')
        }
      })
    } else {
      this.isSubmitting.set(true)
      this.authService.login(username, password).subscribe({
        next: () => {
          this.isSubmitting.set(false)
          this.closeDialog()
        },
        error: (err) => {
          this.isSubmitting.set(false)
          this.errorMessage.set(err?.error?.detail ?? 'Log in failed')
        }
      })
    }
  }

  openProfile() {
    this.router.navigate(['/profile'])
  }

  profileFallback(): string {
    const username = this.authService.username()?.trim() || '?'
    const tokens = username.split(/\s+/).filter(Boolean)
    if (tokens.length === 0) return '?'
    if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase()
    return (tokens[0][0] + tokens[tokens.length - 1][0]).toUpperCase()
  }

  openClaimDialog() {
    this.claimError.set(null)
    this.gamesService.getPlayers().subscribe(players => this.players.set(players))
    this.showDialogModal(this.claimDialog.nativeElement)
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
      error: (err) => this.claimError.set(err?.error?.detail ?? 'Could not claim player')
    })
  }

  unclaim(playerId: number) {
    this.claimError.set(null)
    this.authService.unclaimPlayer(playerId).subscribe({
      error: (err) => this.claimError.set(err?.error?.detail ?? 'Could not unclaim player')
    })
  }

  private showDialogModal(dialog: HTMLDialogElement) {
    this.savedScrollY = window.scrollY
    document.body.style.position = 'fixed'
    document.body.style.top = `-${this.savedScrollY}px`
    document.body.style.width = '100%'
    dialog.showModal()
  }

  private unlockBodyScroll() {
    document.body.style.position = ''
    document.body.style.top = ''
    document.body.style.width = ''
    window.scrollTo(0, this.savedScrollY)
  }
}
