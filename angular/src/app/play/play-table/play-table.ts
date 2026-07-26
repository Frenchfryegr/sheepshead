import { Component, computed, effect, ElementRef, input, output, signal, ViewChild } from '@angular/core'

import { OnlineAction, OnlineCard, OnlineGameView, OnlineHandResult, OnlineSeatPublic } from '../../interfaces/online-game'

@Component({
  selector: 'app-play-table',
  standalone: false,
  templateUrl: './play-table.html',
  styleUrl: './play-table.css',
})
export class PlayTable {
  game = input.required<OnlineGameView>()
  disabled = input.required<boolean>()
  playbackMessage = input.required<string | null>()
  playbackResult = input.required<OnlineHandResult | null>()
  awaitingNextHand = input.required<boolean>()
  animatingCard = input.required<string | null>()
  trickWinnerSeat = input.required<number | null>()
  action = output<OnlineAction>()
  nextHand = output<void>()

  @ViewChild('historyDialog') historyDialog?: ElementRef<HTMLDialogElement>

  /** Keep in step with the `announce` keyframes in play-table.css. */
  private static readonly ANNOUNCEMENT_MS = 3500

  selectedBury = signal<OnlineCard[]>([])
  /** Brief, self-clearing banner naming the contract. Never blocks input. */
  announcement = signal<string | null>(null)
  /** The partner card chosen for an under call, while the face-down card is being picked. */
  pendingUnderCall = signal<OnlineCard | null>(null)
  selectedUnder = signal<OnlineCard | null>(null)

  constructor() {
    effect(() => {
      this.game().hand_number
      this.game().phase
      this.selectedBury.set([])
      this.pendingUnderCall.set(null)
      this.selectedUnder.set(null)
    })

    effect(onCleanup => {
      // `contractText` is a computed, so this only re-runs when the *text* changes — not on
      // every card played. Reading it once per contract is what keeps the timer honest.
      const text = this.contractText()
      if (!text) {
        this.announcement.set(null)
        return
      }
      this.announcement.set(text)
      const timer = setTimeout(() => this.announcement.set(null), PlayTable.ANNOUNCEMENT_MS)
      onCleanup(() => clearTimeout(timer))
    })
  }

  /**
   * What this hand is, once it is settled. Null until the bidding resolves — during `calling`
   * a null `called_card` means "not called yet", which is indistinguishable from going alone,
   * so the phase gate is doing real work rather than being defensive.
   */
  contractText = computed<string | null>(() => {
    const game = this.game()
    if (!['playing', 'hand_done', 'game_over'].includes(game.phase)) return null
    if (game.is_leaster) return 'Leaster — everyone passed'
    if (game.picker_seat === null) return null
    const picker = game.seats[game.picker_seat]?.name ?? 'The picker'
    if (!game.called_card) return `${picker} is going alone`
    const parts = this.cardParts(game.called_card)
    return `${picker} called the ${parts.rank}${parts.suit}`
  })

  humanTurn = computed(() => this.game().turn_seat === this.game().seat)
  humanSeat = computed(() => this.game().seats[this.game().seat])
  opponents = computed(() => this.game().seats.filter(seat => !seat.is_human))
  callActions = computed(() =>
    this.game().legal_actions.filter(
      (action): action is Extract<OnlineAction, { type: 'call' }> => action.type === 'call',
    ),
  )
  underCallActions = computed(() =>
    this.game().legal_actions.filter(
      (action): action is Extract<OnlineAction, { type: 'call_under' }> =>
        action.type === 'call_under',
    ),
  )
  /** Distinct partner cards offered as under calls; each pairs with any card in hand. */
  underCallCards = computed(() => [...new Set(this.underCallActions().map(action => action.card))])
  /** The picker may take their buried cards back until they commit to a call. */
  canUnbury = computed(() => this.game().legal_actions.some(action => action.type === 'unbury'))
  /**
   * Nothing left to call. Reachable by burying away the only suit whose ace was callable — the
   * bury itself is unrestricted, so this is the consequence rather than a blocked move.
   */
  mustGoAlone = computed(() =>
    this.game().phase === 'calling'
    && this.callActions().every(action => action.card === null)
    && this.underCallCards().length === 0,
  )
  playableCards = computed(() =>
    new Set(
      this.game().legal_actions
        .filter((action): action is Extract<OnlineAction, { type: 'play' }> => action.type === 'play')
        .map(action => action.card),
    ),
  )
  latestResult = computed<OnlineHandResult | null>(() => {
    return this.playbackResult()
  })
  /**
   * Interactive prompts render in the floating centre panel. Every phase listed here happens
   * with an empty trick area, so the panel never covers cards in play — which is why status
   * text is handled separately by `statusMessage`.
   */
  showPrompt = computed(() => {
    // Order matters: `disabled` is `submitting || …`, and submitting stays true right through
    // playback — the end-of-hand pause happens *inside* that window, blocked on this panel's
    // own button. Testing disabled first would hide the only way to continue.
    if (this.awaitingNextHand()) return true
    if (this.disabled()) return false
    if (!this.humanTurn()) return false
    return ['picking', 'burying', 'calling'].includes(this.game().phase)
  })

  /**
   * Whether to dim the cards that cannot be played. Keyed on a card having been led rather than
   * on the player's turn, so they can read their options while the trick comes round to them.
   *
   * Legality follows from the led suit alone, so the backend's list is valid for the whole
   * trick — which is what makes showing it early honest rather than a guess. With an empty
   * trick there is nothing to follow and every card is playable, so nothing is dimmed.
   */
  showPlayableHint = computed(() =>
    this.game().phase === 'playing' && this.game().current_trick.length > 0,
  )

  /**
   * Transient status, shown as a slim pill above the trick rather than over it. Null while a
   * prompt is up so the two never talk at once, and during the player's own turn to play —
   * the highlighted cards already say it.
   */
  statusMessage = computed<string | null>(() => {
    if (this.showPrompt() || this.awaitingNextHand()) return null
    const playback = this.playbackMessage()
    if (playback) return playback
    if (this.disabled()) return 'Waiting for the table…'
    if (!this.humanTurn()) {
      const seat = this.game().seats[this.game().turn_seat ?? 0]
      return seat ? `${seat.name} is thinking…` : null
    }
    return null
  })

  hasAction(type: OnlineAction['type']): boolean {
    return this.game().legal_actions.some(action => action.type === type)
  }

  /** Playstyles are shown deliberately: the player is meant to read them and adapt. */
  private static readonly STYLE_LABELS: Record<string, string> = {
    cautious: 'Cautious',
    gambler: 'Gambler',
    grinder: 'Grinder',
    tactician: 'Tactician',
    heuristic: 'Balanced',
    random: 'Random',
  }

  styleLabel(seat: OnlineSeatPublic): string | null {
    if (!seat.ai_strategy) return null
    return PlayTable.STYLE_LABELS[seat.ai_strategy] ?? null
  }

  /**
   * Read straight off the hand state, so it follows the deal round the table on its own —
   * `_deal_hand` rotates `dealer_seat` and `freshDealView` carries the new one into playback.
   */
  isDealer(seat: number): boolean {
    return this.game().dealer_seat === seat
  }

  roleLabel(seat: number): string | null {
    if (this.game().is_leaster) return null
    if (this.game().picker_seat === seat) return 'Picker'
    if (this.game().partner_revealed && this.game().partner_seat === seat) return 'Partner'
    return null
  }

  cardParts(card: OnlineCard): { rank: string, suit: string, red: boolean } {
    const suitCode = card.slice(-1)
    const suits: Record<string, string> = { C: '♣', S: '♠', H: '♥', D: '♦' }
    return {
      rank: card.slice(0, -1).replace('T', '10'),
      suit: suits[suitCode] ?? suitCode,
      red: suitCode === 'H' || suitCode === 'D',
    }
  }

  cardBacks(count: number): number[] {
    return Array.from({ length: count }, (_, index) => index)
  }

  chooseCard(card: OnlineCard): void {
    if (this.disabled() || !this.humanTurn()) return
    if (this.game().phase === 'playing' && this.playableCards().has(card)) {
      this.action.emit({ type: 'play', card })
      return
    }
    if (this.pendingUnderCall()) {
      this.selectedUnder.set(this.selectedUnder() === card ? null : card)
      return
    }
    if (this.game().phase !== 'burying') return
    const selected = this.selectedBury()
    if (selected.includes(card)) {
      this.selectedBury.set(selected.filter(value => value !== card))
    } else if (selected.length < this.game().ruleset.blind_size) {
      this.selectedBury.set([...selected, card])
    }
  }

  confirmBury(): void {
    const cards = this.selectedBury()
    const isLegal = this.game().legal_actions.some(
      action => action.type === 'bury'
        && action.cards.length === cards.length
        && action.cards.every(card => cards.includes(card)),
    )
    if (isLegal) this.action.emit({ type: 'bury', cards })
  }

  emitSimple(type: 'pick' | 'pass'): void {
    if (!this.disabled() && this.hasAction(type)) this.action.emit({ type })
  }

  call(card: OnlineCard | null): void {
    if (!this.disabled()) this.action.emit({ type: 'call', card })
  }

  unbury(): void {
    if (!this.disabled()) this.action.emit({ type: 'unbury' })
  }

  startUnderCall(card: OnlineCard): void {
    this.pendingUnderCall.set(card)
    this.selectedUnder.set(null)
  }

  cancelUnderCall(): void {
    this.pendingUnderCall.set(null)
    this.selectedUnder.set(null)
  }

  confirmUnderCall(): void {
    const card = this.pendingUnderCall()
    const under = this.selectedUnder()
    if (this.disabled() || !card || !under) return
    // Only emit a pairing the backend actually offered.
    const isLegal = this.underCallActions().some(
      action => action.card === card && action.under === under,
    )
    if (isLegal) this.action.emit({ type: 'call_under', card, under })
  }

  openHistory(): void {
    this.historyDialog?.nativeElement.showModal()
  }

  closeHistory(): void {
    this.historyDialog?.nativeElement.close()
  }

  resultTitle(result: OnlineHandResult): string {
    if (result.kind === 'leaster') {
      // A tied leaster has no winner at all and nobody scores, so there is no seat to name.
      if (result.leaster_winner === null) return 'Leaster tied — nobody scores'
      return `${this.game().seats[result.leaster_winner]?.name} won the leaster`
    }
    return result.kind === 'picker_win' ? 'Picker team won' : 'Picker team lost'
  }
}
