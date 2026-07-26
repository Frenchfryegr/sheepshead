import { isPlatformBrowser } from '@angular/common'
import { Component, inject, OnDestroy, OnInit, PLATFORM_ID, signal } from '@angular/core'
import { HttpErrorResponse } from '@angular/common/http'

import { OnlineAction, OnlineEvent, OnlineGameSummary, OnlineGameView, OnlineHandResult, OnlinePlaystyle } from '../../interfaces/online-game'
import { TableDisplay } from '../../games/table-display'
import { OnlineGameService } from '../online-game-service'

type GameSpeed = 'slow' | 'medium' | 'fast'

@Component({
  selector: 'app-play',
  standalone: false,
  templateUrl: './play.html',
  styleUrl: './play.css',
})
export class Play implements OnInit, OnDestroy {
  private service = inject(OnlineGameService)
  private tableDisplay = inject(TableDisplay)
  private isBrowser = isPlatformBrowser(inject(PLATFORM_ID))

  games = signal<OnlineGameSummary[]>([])
  activeGame = signal<OnlineGameView | null>(null)
  submitting = signal(false)
  loading = signal(true)
  error = signal<string | null>(null)
  playbackMessage = signal<string | null>(null)
  playbackResult = signal<OnlineHandResult | null>(null)
  awaitingNextHand = signal(false)
  animatingCard = signal<string | null>(null)
  trickWinnerSeat = signal<number | null>(null)
  gameMenuOpen = signal(false)
  gameSpeed = signal<GameSpeed>('fast')
  readonly gameSpeeds: GameSpeed[] = ['slow', 'medium', 'fast']
  /** '' means a mixed table: the backend deals playstyles out at random. */
  tableStyle = signal('')
  playstyles = signal<OnlinePlaystyle[]>([])
  private nextHandResolve: (() => void) | null = null
  private playbackRun = 0

  ngOnInit(): void {
    if (!this.isBrowser) return
    this.refreshGames()
    // Best-effort: the chooser just falls back to a mixed table if this fails.
    this.service.listPlaystyles().subscribe({ next: styles => this.playstyles.set(styles) })
  }

  ngOnDestroy(): void {
    void this.tableDisplay.disable()
  }

  refreshGames(): void {
    this.loading.set(true)
    this.service.listMyGames().subscribe({
      next: games => {
        this.games.set(games)
        this.loading.set(false)
      },
      error: error => {
        this.handleError(error)
        this.loading.set(false)
      },
    })
  }

  createGame(): void {
    if (this.submitting()) return
    this.submitting.set(true)
    this.error.set(null)
    const style = this.tableStyle()
    this.service.createGame(style ? { ai_strategies: style } : {}).subscribe({
      next: game => {
        this.submitting.set(false)
        void this.presentResponse(game)
        this.refreshGames()
      },
      error: error => {
        this.submitting.set(false)
        this.handleError(error)
      },
    })
  }

  resume(game: OnlineGameSummary): void {
    this.error.set(null)
    this.service.getGame(game.online_game_id).subscribe({
      next: view => {
        this.activeGame.set(view)
        this.enableTableDisplay()
      },
      error: error => this.handleError(error),
    })
  }

  closeTable(): void {
    this.playbackRun += 1
    this.activeGame.set(null)
    this.playbackMessage.set(null)
    this.animatingCard.set(null)
    this.trickWinnerSeat.set(null)
    this.gameMenuOpen.set(false)
    this.continueToNextHand()
    void this.tableDisplay.disable()
    this.refreshGames()
  }

  continueToNextHand(): void {
    this.awaitingNextHand.set(false)
    this.playbackResult.set(null)
    this.nextHandResolve?.()
    this.nextHandResolve = null
  }

  setGameSpeed(speed: GameSpeed): void {
    this.gameSpeed.set(speed)
    this.gameMenuOpen.set(false)
  }

  sendAction(action: OnlineAction): void {
    const game = this.activeGame()
    if (!game || this.submitting()) return
    this.submitting.set(true)
    this.error.set(null)
    this.service.sendAction(game.online_game_id, game.version, action).subscribe({
      next: response => void this.presentResponse(response),
      error: error => {
        this.submitting.set(false)
        if (error instanceof HttpErrorResponse && error.status === 409) {
          this.reloadActiveGame(game.online_game_id)
        } else {
          this.handleError(error)
        }
      },
    })
  }

  abandonSummary(game: OnlineGameSummary): void {
    if (this.submitting()) return
    this.submitting.set(true)
    this.service.abandon(game.online_game_id, game.version).subscribe({
      next: () => {
        this.submitting.set(false)
        this.refreshGames()
      },
      error: error => {
        this.submitting.set(false)
        if (error instanceof HttpErrorResponse && error.status === 409) {
          this.refreshGames()
        } else {
          this.handleError(error)
        }
      },
    })
  }

  abandonActive(): void {
    const game = this.activeGame()
    if (!game || this.submitting()) return
    this.submitting.set(true)
    this.service.abandon(game.online_game_id, game.version).subscribe({
      next: () => {
        this.submitting.set(false)
        this.closeTable()
      },
      error: error => {
        this.submitting.set(false)
        if (error instanceof HttpErrorResponse && error.status === 409) {
          this.reloadActiveGame(game.online_game_id)
        } else {
          this.handleError(error)
        }
      },
    })
  }

  private reloadActiveGame(id: number): void {
    this.service.getGame(id).subscribe({
      next: view => {
        this.activeGame.set(view)
        this.submitting.set(false)
      },
      error: error => {
        this.submitting.set(false)
        this.handleError(error)
      },
    })
  }

  private async presentResponse(response: OnlineGameView): Promise<void> {
    const run = ++this.playbackRun
    if (!this.isBrowser) {
      this.activeGame.set(response)
      this.submitting.set(false)
      return
    }
    // A freshly created game has nothing on screen yet, and playback only advances a view that
    // already exists — so without this the table stayed blank until the drive loop's events had
    // all played, i.e. until an AI picked or the turn reached the player. Seed the deal first so
    // the hand is visible while the bidding is narrated.
    if (!this.activeGame()) {
      this.activeGame.set(this.freshDealView(response))
      this.enableTableDisplay()
    }
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    for (const event of response.events) {
      if (run !== this.playbackRun) return
      this.playbackMessage.set(this.describeEvent(event, response))
      const current = this.activeGame()
      if (current) {
        this.activeGame.set(this.applyPlaybackEvent(current, event, response))
      }
      this.animatingCard.set(
        event.type === 'card_played' && event.seat !== undefined && event.card
          ? `${event.seat}:${event.card}`
          : null,
      )
      this.trickWinnerSeat.set(
        event.type === 'trick_won' && event.seat !== undefined ? event.seat : null,
      )
      if (event.type === 'hand_scored' && event.result) {
        this.playbackResult.set(event.result)
        this.awaitingNextHand.set(true)
        await new Promise<void>(resolve => {
          this.nextHandResolve = resolve
        })
      }
      const delay = reducedMotion ? 80 : this.playbackDelay(event)
      await new Promise(resolve => setTimeout(resolve, delay))
      if (event.type === 'trick_won') {
        const displayed = this.activeGame()
        if (displayed) {
          const swept = this.cloneView(displayed)
          swept.current_trick = []
          this.activeGame.set(swept)
        }
        this.trickWinnerSeat.set(null)
      }
    }
    if (run !== this.playbackRun) return
    this.activeGame.set(response)
    this.enableTableDisplay()
    this.animatingCard.set(null)
    this.trickWinnerSeat.set(null)
    this.playbackMessage.set(null)
    this.submitting.set(false)
  }

  private applyPlaybackEvent(
    view: OnlineGameView,
    event: OnlineEvent,
    response: OnlineGameView,
  ): OnlineGameView {
    // A new deal cannot be derived from the hand that just ended — the player's cards are
    // all gone by then. Rebuild it from the response, which carries the fresh hand.
    if (event.type === 'new_hand') return this.freshDealView(response)

    const next = this.cloneView(view)
    next.events = []
    switch (event.type) {
      case 'card_played':
        // A masked under arrives with no card but must still animate into the trick.
        if (event.seat === undefined || (!event.card && !event.under)) break
        if (!next.current_trick.some(play => play.seat === event.seat)) {
          next.current_trick.push({
            seat: event.seat,
            card: event.card ?? null,
            under: event.under,
          })
        }
        if (event.seat === next.seat) {
          next.hand = next.hand.filter(card => card !== event.card)
        }
        if (next.seats[event.seat]) {
          next.seats[event.seat].card_count = Math.max(0, next.seats[event.seat].card_count - 1)
        }
        next.turn_seat = (event.seat + 1) % next.ruleset.num_players
        break
      case 'trick_won':
        if (event.seat !== undefined && next.seats[event.seat]) {
          next.seats[event.seat].trick_count += 1
          next.turn_seat = event.seat
        }
        // The displayed legal actions belong to the trick that just ended, and go stale the
        // moment a new one starts. The response's are for the trick about to be led, and are
        // valid from its first card: what a player may follow with depends on the led suit,
        // not on how many have played after it.
        next.legal_actions = response.legal_actions
        break
      case 'passed':
        if (event.seat === undefined) break
        if (!next.passes.includes(event.seat)) next.passes.push(event.seat)
        // Move the turn marker along with the bidding. Only card_played used to do this, which
        // was invisible while the table did not render until the bidding was over.
        next.turn_seat = (event.seat + 1) % next.ruleset.num_players
        if (next.passes.length === next.ruleset.num_players) {
          // Everyone passed: the contract is settled as a leaster. There is no event of its
          // own for this, so the last pass is what establishes it.
          next.is_leaster = true
          next.phase = 'playing'
        }
        break
      case 'picked':
        if (event.seat === undefined) break
        next.picker_seat = event.seat
        next.turn_seat = event.seat
        break
      case 'called':
        next.called_card = event.card ?? null
        // Advancing the phase here is what lets the contract announcement fire at the right
        // moment in the narration rather than after the whole drive loop. `contractText()`
        // stays null until `playing` because a null called_card during `calling` means "not
        // called yet", which is indistinguishable from going alone.
        next.phase = 'playing'
        break
      case 'partner_revealed':
        if (event.seat !== undefined) {
          next.partner_revealed = true
          next.partner_seat = event.seat
        }
        break
      case 'hand_scored':
        if (event.result) {
          next.scores = next.scores.map(
            (score, seat) => score + (event.result?.deltas[seat] ?? 0),
          )
          if (!next.hand_history.some(result => result.hand_number === event.result?.hand_number)) {
            next.hand_history.push(event.result)
          }
        }
        break
    }
    return next
  }

  private cloneView(view: OnlineGameView): OnlineGameView {
    return JSON.parse(JSON.stringify(view)) as OnlineGameView
  }

  /**
   * The state a freshly dealt hand starts from, rewound out of a response.
   *
   * Used at both points where a deal appears with nothing to advance from: creating a game
   * (no view on screen at all) and the `new_hand` event mid-playback (the previous hand's view
   * is useless — the player's cards are all gone by then, which is why their hand showed as
   * empty for the whole of the next hand's bidding).
   *
   * The response already reflects every AI action the drive loop took, so showing it directly
   * would spoil the bidding the playback is about to narrate — the picker, the called card, and
   * any cards already on the table. This is an exact reconstruction rather than a guess: a deal
   * always begins with full hands, nobody passed, and the turn on the dealer's left. The
   * player's own cards need no rewind either way, because a response contains at most one human
   * action and it comes before any of this.
   */
  private freshDealView(response: OnlineGameView): OnlineGameView {
    const view = this.cloneView(response)
    view.phase = 'picking'
    view.passes = []
    view.picker_seat = null
    view.called_card = null
    view.under_card = null
    view.partner_revealed = false
    view.partner_seat = null
    view.is_leaster = false
    view.current_trick = []
    view.completed_tricks = []
    view.turn_seat = (view.dealer_seat + 1) % view.ruleset.num_players
    for (const seat of view.seats) {
      seat.card_count = view.ruleset.cards_per_player
      seat.trick_count = 0
      seat.taken_points = 0
    }
    // The player's own hand needs no rewind: creation stops at their first decision, so they
    // have neither picked up the blind nor played a card.
    return view
  }

  private playbackDelay(event: OnlineEvent): number {
    const timings: Record<GameSpeed, { card: number, trick: number, other: number }> = {
      fast: { card: 260, trick: 420, other: 150 },
      medium: { card: 450, trick: 700, other: 250 },
      slow: { card: 750, trick: 1100, other: 400 },
    }
    const speed = timings[this.gameSpeed()]
    if (event.type === 'card_played') return speed.card
    if (event.type === 'trick_won') return speed.trick
    return speed.other
  }

  private enableTableDisplay(): void {
    // No element argument, so no browser fullscreen: the table fills the viewport through CSS
    // alone. Wake lock and the dark canvas still apply.
    if (this.isBrowser) void this.tableDisplay.enable()
  }

  private describeEvent(event: OnlineEvent, game: OnlineGameView): string {
    const name = event.seat === undefined ? '' : game.seats[event.seat]?.name ?? `Seat ${event.seat + 1}`
    switch (event.type) {
      case 'picked': return `${name} picked`
      case 'passed': return `${name} passed`
      case 'buried': return `${name} buried two cards`
      case 'unburied': return `${name} is choosing again`
      case 'called': return event.card ? `${name} called ${event.card}` : `${name} is going alone`
      case 'card_played': return `${name} played a card`
      case 'trick_won': return `${name} took the trick`
      case 'partner_revealed': return `${name} is the partner`
      case 'hand_scored': return 'Hand scored'
      case 'new_hand': return `Dealing hand ${event.hand_number}`
      default: return 'Table updated'
    }
  }

  private handleError(error: unknown): void {
    if (error instanceof HttpErrorResponse) {
      this.error.set(error.error?.detail || error.message || 'Online play request failed')
    } else {
      this.error.set('Online play request failed')
    }
  }
}
