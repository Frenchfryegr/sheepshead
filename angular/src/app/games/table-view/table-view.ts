import { Component, computed, effect, ElementRef, inject, input, OnDestroy, output, signal, untracked, ViewChild } from '@angular/core'
import { Player } from '../../interfaces/player'
import { PlayerRoundScore } from '../../interfaces/round'
import { ScoreTable } from '../../interfaces/score-table'
import { scoreboardColor, scoreboardTextColor } from '../player-display'
import { TableSeatStore } from '../table-seat-store'

// The guided round-entry flow. Which steps actually run depends on player count and result —
// see stepSequence().
export type TableStep = 'idle' | 'dealer' | 'result' | 'picker' | 'partner' | 'modifiers'

export interface Seat {
  player: Player
  index: number
  xPct: number
  yPct: number
  total: number
  initials: string
  color: string
  textColor: string
}

const RING_RADIUS_PCT = 38
const LONG_PRESS_MS = 400
// Pointer travel that turns a press into a drag/scroll rather than a tap.
const MOVE_TOLERANCE_PX = 10
// Max distance from a seat centre for it to count as a drop target.
const DROP_RADIUS_PX = 70

@Component({
  selector: 'app-table-view',
  standalone: false,
  templateUrl: './table-view.html',
  styleUrl: './table-view.css',
})
export class TableView implements OnDestroy {
  private seatStore = inject(TableSeatStore)

  // --- Inputs: everything is owned by Games; this component only renders and emits intent. ---
  gameId = input.required<number | null>()
  players = input.required<Player[]>()
  scoreTable = input.required<ScoreTable>()
  roundNumber = input.required<number>()
  isDealerGame = input.required<boolean>()
  canEdit = input.required<boolean>()
  submitting = input.required<boolean>()

  result = input.required<string>()
  pickerId = input.required<number | null>()
  partnerId = input.required<number | null>()
  dealerId = input.required<number | null>()
  noPartner = input.required<boolean>()
  noSchneider = input.required<boolean>()
  noTrick = input.required<boolean>()
  previewScores = input.required<PlayerRoundScore[]>()

  // --- Outputs: wired straight to the existing handlers on Games. ---
  resultChange = output<string>()
  pickerChange = output<number | null>()
  partnerChange = output<number | null>()  // -1 means "No Partner", same sentinel as the form
  dealerChange = output<number | null>()
  noSchneiderChange = output<boolean>()
  noTrickChange = output<boolean>()
  // Deliberately not named `submit`/`cancel`: both are native DOM event names (form submit,
  // dialog cancel) and this component lives inside a <dialog>, so a bubbling native event
  // could fire the output binding.
  roundSubmit = output<void>()
  roundCancel = output<void>()
  exit = output<void>()

  @ViewChild('ring') ringElement?: ElementRef<HTMLElement>

  step = signal<TableStep>('idle')
  seatEditMode = signal(false)
  drawerOpen = signal(false)
  seatOrder = signal<number[]>([])
  dragIndex = signal<number | null>(null)
  dropIndex = signal<number | null>(null)
  dragPos = signal<{ x: number, y: number } | null>(null)

  private pressTimer: ReturnType<typeof setTimeout> | null = null
  private pressSeat: Seat | null = null
  private pressOrigin: { x: number, y: number } | null = null
  private movedDuringPress = false
  private longPressFired = false
  private lastPointer = { x: 0, y: 0 }
  private wasSubmitting = false

  constructor() {
    // Re-seed seat order from storage whenever the roster or the game changes. Does not read
    // seatOrder, so swapping seats (which writes it) can't re-trigger this.
    effect(() => {
      this.seatOrder.set(this.seatStore.order(this.gameId(), this.players()))
    })

    // Games flips isSubmittingRound back to false via resetRoundForm() once the round is
    // saved, which is our signal that the round landed and the hub should go back to idle.
    // (A failed submit leaves it true — same stuck-on-"Submitting…" behaviour as the form.)
    effect(() => {
      const submitting = this.submitting()
      untracked(() => {
        if (this.wasSubmitting && !submitting) this.step.set('idle')
        this.wasSubmitting = submitting
      })
    })
  }

  ngOnDestroy() {
    this.clearPressTimer()
  }

  // ---------------------------------------------------------------- layout

  orderedPlayers = computed<Player[]>(() => {
    const byId = new Map(this.players().map(p => [p.player_id, p]))
    return this.seatOrder()
      .map(id => byId.get(id))
      .filter((p): p is Player => !!p)
  })

  // Running total per player = the last scoreboard row's totals.
  totals = computed<Map<number, number>>(() => {
    const rows = this.scoreTable().rows
    return rows.length > 0 ? rows[rows.length - 1].totals : new Map<number, number>()
  })

  // Seat 0 sits at the bottom of the ring (nearest whoever set the phone down); seats advance
  // clockwise. Icons are NOT rotated to face their seat — everything reads upright in one
  // direction, which tested better than per-seat rotation.
  seats = computed<Seat[]>(() => {
    const players = this.orderedPlayers()
    const count = players.length
    const initials = this.scoreTable().initials
    const totals = this.totals()

    return players.map((player, index) => {
      const angle = (index / count) * 2 * Math.PI + Math.PI / 2
      return {
        player,
        index,
        xPct: 50 + Math.cos(angle) * RING_RADIUS_PCT,
        yPct: 50 + Math.sin(angle) * RING_RADIUS_PCT,
        total: totals.get(player.player_id) ?? 0,
        initials: initials.get(player.player_id) ?? '??',
        color: scoreboardColor(player),
        textColor: scoreboardTextColor(player),
      }
    })
  })

  // ---------------------------------------------------------------- step machine

  isLeaster = computed(() => this.result() === 'Leaster')
  // Mirrors showPartnerSelect() in Games: 5-player, non-leaster rounds only.
  showPartnerStep = computed(() => this.players().length === 5 && !this.isLeaster())

  stepSequence = computed<TableStep[]>(() => {
    const steps: TableStep[] = []
    if (this.isDealerGame()) steps.push('dealer')
    steps.push('result', 'picker')
    if (this.showPartnerStep()) steps.push('partner')
    steps.push('modifiers')
    return steps
  })

  canSubmit = computed(() =>
    !!this.pickerId() && !!this.result() && !this.submitting() &&
    (!this.isDealerGame() || !!this.dealerId())
  )

  startRound() {
    if (!this.canEdit() || this.seatEditMode()) return
    this.step.set(this.stepSequence()[0])
  }

  private advance() {
    const sequence = this.stepSequence()
    const next = sequence[sequence.indexOf(this.step()) + 1]
    if (next) this.step.set(next)
  }

  // Walks back one step and clears whatever that step chose, so the user re-picks it.
  stepBack() {
    const sequence = this.stepSequence()
    const previous = sequence[sequence.indexOf(this.step()) - 1]
    if (!previous) {
      this.cancelRound()
      return
    }
    this.step.set(previous)
    switch (previous) {
      case 'dealer': this.dealerChange.emit(null); break
      case 'result': this.resultChange.emit(''); break
      case 'picker': this.pickerChange.emit(null); break
      case 'partner': this.partnerChange.emit(null); break
    }
  }

  cancelRound() {
    this.step.set('idle')
    this.roundCancel.emit()
  }

  chooseResult(result: string) {
    this.resultChange.emit(result)
    this.advance()
  }

  chooseNoPartner() {
    this.partnerChange.emit(-1)
    this.advance()
  }

  submitRound() {
    if (!this.canSubmit()) return
    this.roundSubmit.emit()
  }

  // ---------------------------------------------------------------- seat interaction

  // The dealer sits out, so they can't take a round role — but their icon still renders.
  private isSittingOut(seat: Seat): boolean {
    return this.isDealerGame() && seat.player.player_id === this.dealerId()
  }

  isSelectable(seat: Seat): boolean {
    if (!this.canEdit() || this.seatEditMode()) return false
    switch (this.step()) {
      case 'dealer': return true
      case 'picker': return !this.isSittingOut(seat)
      case 'partner': return !this.isSittingOut(seat) && seat.player.player_id !== this.pickerId()
      default: return false
    }
  }

  // Dim seats that aren't part of the current prompt, so the table can see where to tap.
  isDimmed(seat: Seat): boolean {
    const step = this.step()
    if (step === 'idle' || this.seatEditMode()) return false
    if (step === 'result' || step === 'modifiers') return this.isSittingOut(seat)
    return !this.isSelectable(seat) && !this.roleBadge(seat)
  }

  roleBadge(seat: Seat): string | null {
    const id = seat.player.player_id
    if (id === this.dealerId()) return 'D'
    if (id === this.pickerId()) return this.isLeaster() ? 'LW' : 'P'
    if (id === this.partnerId()) return 'PT'
    return null
  }

  previewDelta(seat: Seat): number | null {
    if (this.step() !== 'modifiers') return null
    const score = this.previewScores().find(s => s.player_id === seat.player.player_id)
    if (!score || score.player_role === 'Dealer') return null
    return score.point_delta
  }

  private handleSeatTap(seat: Seat) {
    if (!this.isSelectable(seat)) return
    switch (this.step()) {
      case 'dealer':
        this.dealerChange.emit(seat.player.player_id)
        break
      case 'picker':
        this.pickerChange.emit(seat.player.player_id)
        break
      case 'partner':
        this.partnerChange.emit(seat.player.player_id)
        break
      default:
        return
    }
    this.advance()
  }

  // ---------------------------------------------------------------- drag to rearrange

  onSeatPointerDown(seat: Seat, event: PointerEvent) {
    if (this.drawerOpen()) return
    this.lastPointer = { x: event.clientX, y: event.clientY }
    this.pressSeat = seat
    this.pressOrigin = { x: event.clientX, y: event.clientY }
    this.movedDuringPress = false
    this.longPressFired = false
    ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)

    if (this.seatEditMode()) {
      // Already rearranging — every press is a drag.
      this.dragIndex.set(seat.index)
      this.dragPos.set(this.toLocal(event))
      return
    }
    // Long-press only enters rearrange mode, and only when no round is being entered.
    if (this.step() !== 'idle') return
    this.pressTimer = setTimeout(() => {
      this.longPressFired = true
      this.seatEditMode.set(true)
      this.dragIndex.set(seat.index)
      this.dragPos.set(this.toLocalPoint(this.lastPointer))
    }, LONG_PRESS_MS)
  }

  onPointerMove(event: PointerEvent) {
    this.lastPointer = { x: event.clientX, y: event.clientY }

    if (this.pressOrigin && !this.movedDuringPress) {
      const distance = Math.hypot(event.clientX - this.pressOrigin.x, event.clientY - this.pressOrigin.y)
      if (distance > MOVE_TOLERANCE_PX) {
        this.movedDuringPress = true
        // Moving before the timer fires means a swipe, not a long press.
        if (!this.seatEditMode()) this.clearPressTimer()
      }
    }

    if (this.dragIndex() === null) return
    event.preventDefault()
    this.dragPos.set(this.toLocal(event))
    this.dropIndex.set(this.nearestSeatIndex(event))
  }

  onPointerUp() {
    this.clearPressTimer()
    const dragging = this.dragIndex()

    if (dragging !== null) {
      const target = this.dropIndex()
      if (target !== null && target !== dragging) this.swapSeats(dragging, target)
      this.dragIndex.set(null)
      this.dropIndex.set(null)
      this.dragPos.set(null)
    } else if (this.pressSeat && !this.movedDuringPress && !this.longPressFired) {
      this.handleSeatTap(this.pressSeat)
    }

    this.pressSeat = null
    this.pressOrigin = null
  }

  onPointerCancel() {
    this.clearPressTimer()
    this.dragIndex.set(null)
    this.dropIndex.set(null)
    this.dragPos.set(null)
    this.pressSeat = null
    this.pressOrigin = null
  }

  endSeatEdit() {
    this.seatEditMode.set(false)
    this.onPointerCancel()
  }

  // Swap rather than insert-and-shift: on a small ring it's easier to predict and it undoes
  // itself when repeated.
  private swapSeats(from: number, to: number) {
    const order = [...this.seatOrder()]
    if (from >= order.length || to >= order.length) return
    ;[order[from], order[to]] = [order[to], order[from]]
    this.seatOrder.set(order)
    this.seatStore.save(this.gameId(), order)
  }

  private nearestSeatIndex(event: PointerEvent): number | null {
    const rect = this.ringElement?.nativeElement.getBoundingClientRect()
    if (!rect) return null
    let nearest: number | null = null
    let nearestDistance = DROP_RADIUS_PX
    for (const seat of this.seats()) {
      const seatX = rect.left + (seat.xPct / 100) * rect.width
      const seatY = rect.top + (seat.yPct / 100) * rect.height
      const distance = Math.hypot(event.clientX - seatX, event.clientY - seatY)
      if (distance < nearestDistance) {
        nearestDistance = distance
        nearest = seat.index
      }
    }
    return nearest
  }

  private toLocal(event: PointerEvent): { x: number, y: number } {
    return this.toLocalPoint({ x: event.clientX, y: event.clientY })
  }

  private toLocalPoint(point: { x: number, y: number }): { x: number, y: number } {
    const rect = this.ringElement?.nativeElement.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return { x: point.x - rect.left, y: point.y - rect.top }
  }

  private clearPressTimer() {
    if (this.pressTimer !== null) {
      clearTimeout(this.pressTimer)
      this.pressTimer = null
    }
  }

  // ---------------------------------------------------------------- drawer

  playerColor(player: Player): string {
    return scoreboardColor(player)
  }

  playerTextColor(player: Player): string {
    return scoreboardTextColor(player)
  }

  toggleDrawer() {
    // Never let the scoreboard cover a round in progress.
    if (this.step() !== 'idle') return
    this.endSeatEdit()
    this.drawerOpen.update(open => !open)
  }
}
