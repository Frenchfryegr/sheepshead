import { AfterViewInit, Component, computed, HostListener, inject, signal, ViewChild, ElementRef } from '@angular/core';
import { DatePipe, formatDate } from '@angular/common';
import { GamesService } from '../games-service';
import { GameRealtimeService } from '../game-realtime-service';
import { AuthService } from '../../auth/auth-service';
import { Game } from '../../interfaces/game';
import { Player } from '../../interfaces/player';
import { PlayerRoundScore, PlayerRole, Round } from '../../interfaces/round';

interface RoundHistoryEntry {
  round_id: number
  round_number: number
  round_result: string
  no_schneider: boolean
  no_partner: boolean
  no_trick: boolean
  scores: PlayerRoundScore[]
}

interface ScoreTableRow {
  round_number: number
  totals: Map<number, number>
  pickerId: number | null
  partnerId: number | null
  dealerId: number | null
}

interface ScoreTable {
  players: Player[]
  initials: Map<number, string>
  rows: ScoreTableRow[]
  winnerIds: Set<number>
}

type GameSortColumn = 'game_datetime' | 'num_players' | 'rounds' | 'status' | 'winner'
type SortDirection = 'asc' | 'desc'

@Component({
  selector: 'app-games',
  standalone: false,
  templateUrl: './games.html',
  styleUrl: './games.css',
})
export class Games implements AfterViewInit {
  private gamesService = inject(GamesService)
  private gameRealtime = inject(GameRealtimeService)
  protected authService = inject(AuthService)
  private gamesSignal = signal<Game[]>([])
  games = this.gamesSignal.asReadonly()

  sortColumn = signal<GameSortColumn>('game_datetime')
  sortDirection = signal<SortDirection>('desc')
  sortedGames = computed(() => {
    const column = this.sortColumn()
    const multiplier = this.sortDirection() === 'asc' ? 1 : -1
    return [...this.games()].sort((a, b) => multiplier * this.compareGames(a, b, column))
  })

  selectedGame: Game | null = null

  @ViewChild('ShowGameRounds') showGameRoundsDialog!: ElementRef<HTMLDialogElement>
  @ViewChild('GameWizardDialog') gameWizardDialog!: ElementRef<HTMLDialogElement>
  @ViewChild('gameNameField') gameNameField?: ElementRef<HTMLInputElement>
  @ViewChild('selectedGameNameField') selectedGameNameField?: ElementRef<HTMLInputElement>

  private savedScrollY = 0

  @HostListener('document:click', ['$event'])
  onDocumentClickForGameName(event: MouseEvent) {
    const target = event.target as Node
    if (this.editingGameName() && this.gameNameField && !this.gameNameField.nativeElement.contains(target)) {
      this.saveGameName()
    }
    if (this.editingSelectedGameName() && this.selectedGameNameField && !this.selectedGameNameField.nativeElement.contains(target)) {
      this.saveSelectedGameName()
    }
  }

  ngAfterViewInit() {
    this.showGameRoundsDialog.nativeElement.addEventListener('close', () => this.unlockBodyScroll())
    this.gameWizardDialog.nativeElement.addEventListener('close', () => this.unlockBodyScroll())
  }

  private showDialogModal(dialog: HTMLDialogElement) {
    this.lockBodyScroll()
    dialog.showModal()
  }

  private lockBodyScroll() {
    this.savedScrollY = window.scrollY
    document.body.style.position = 'fixed'
    document.body.style.top = `-${this.savedScrollY}px`
    document.body.style.width = '100%'
  }

  private unlockBodyScroll() {
    document.body.style.position = ''
    document.body.style.top = ''
    document.body.style.width = ''
    window.scrollTo(0, this.savedScrollY)
  }

  step = signal<'idle' | 'players' | 'rounds'>('idle')
  existingPlayers = signal<Player[]>([])
  newGamePlayers = signal<Player[]>([])
  newPlayerName = signal('')
  addPlayerFormOpen = signal(false)
  playerSearchQuery = signal('')
  showPlayerDropdown = signal(false)
  newGameId = signal<number | null>(null)
  newGameDatetime = signal<string | null>(null)
  newGameName = signal<string | null>(null)
  editingGameName = signal(false)
  gameNameInput = signal('')
  editingSelectedGameName = signal(false)
  selectedGameNameInput = signal('')
  currentRoundNumber = signal(1)
  roundPickerPlayerId = signal<number | null>(null)
  roundPartnerPlayerId = signal<number | null>(null)
  roundResult = signal<string>('')
  roundNoSchneider = signal(false)
  roundNoPartner = signal(false)
  roundNoTrick = signal(false)
  roundDealerPlayerId = signal<number | null>(null)
  isSubmittingRound = signal(false)
  roundHistory = signal<RoundHistoryEntry[]>([])
  editingRoundId = signal<number | null>(null)
  roundActionsMenuOpen = signal(false)
  completedActionsMenuOpen = signal(false)
  addRoundFormOpen = signal(false)

  isLeasterRound = computed(() => this.roundResult() === 'Leaster')
  showPartnerSelect = computed(() => this.newGamePlayers().length === 5 && !this.isLeasterRound())
  partnerSelectValue = computed(() => this.roundNoPartner() ? -1 : this.roundPartnerPlayerId())
  isDealerGame = computed(() => this.newGamePlayers().length === 4)
  isValidPlayerCount = computed(() => [3, 4, 5].includes(this.newGamePlayers().length))
  activeRoundPlayers = computed(() => {
    const players = this.newGamePlayers()
    if (!this.isDealerGame()) return players
    const dealerId = this.roundDealerPlayerId()
    return dealerId ? players.filter(p => p.player_id !== dealerId) : []
  })

  roundPlayerScores = computed(() => this.calculatePlayerScores())
  activeScoreTable = computed(() => this.buildScoreTable(this.newGamePlayers(), this.roundHistory()))
  activeRoundNumber = computed(() => {
    const editingId = this.editingRoundId()
    if (editingId) {
      return this.roundHistory().find(entry => entry.round_id === editingId)?.round_number ?? this.currentRoundNumber()
    }
    return this.currentRoundNumber()
  })

  constructor() {
    this.refreshGames()
    this.gameRealtime.updates.subscribe(() => this.refetchCurrentGame())
    this.gameRealtime.listUpdates.subscribe(() => this.refreshGames())
    this.gameRealtime.connectList()
  }

  private refetchCurrentGame() {
    const gameId = this.newGameId()
    if (!gameId) return
    this.gamesService.getGames().subscribe(games => {
      this.gamesSignal.set(games)
      const updatedGame = games.find(g => g.game_id === gameId)
      if (updatedGame) this.refreshWizardRoundState(updatedGame)
    })
  }

  refreshGames() {
    this.gamesService.getGames().subscribe(games => this.gamesSignal.set(games))
  }

  toggleDateSort() {
    if (this.sortColumn() === 'game_datetime') {
      this.sortDirection.update(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      this.sortColumn.set('game_datetime')
      this.sortDirection.set('desc')
    }
  }

  toggleSort(column: GameSortColumn) {
    if (this.sortColumn() === column) {
      this.sortDirection.update(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      this.sortColumn.set(column)
      this.sortDirection.set('asc')
    }
  }

  private compareGames(a: Game, b: Game, column: GameSortColumn): number {
    switch (column) {
      case 'game_datetime':
        return new Date(this.normalizeDatetime(a.game_datetime)).getTime() - new Date(this.normalizeDatetime(b.game_datetime)).getTime()
      case 'num_players':
        return a.num_players - b.num_players
      case 'rounds':
        return a.Rounds.length - b.Rounds.length
      case 'status':
        return Number(a.is_completed) - Number(b.is_completed)
      case 'winner':
        return this.getGameWinnerName(a).localeCompare(this.getGameWinnerName(b))
    }
  }

  getGameWinnerName(game: Game): string {
    if (!game.Rounds || game.Rounds.length === 0) return '—'

    const totals = new Map<number, number>()
    for (const round of game.Rounds) {
      for (const score of round.PlayerRoundScore) {
        totals.set(score.player_id, (totals.get(score.player_id) ?? 0) + score.point_delta)
      }
    }

    if (totals.size === 0) return '—'
    const highestTotal = Math.max(...totals.values())
    const winnerIds = new Set([...totals.entries()].filter(([, total]) => total === highestTotal).map(([playerId]) => playerId))

    const winnerNames = game.Players_X_Games
      .map(pxg => pxg.Players)
      .filter(player => winnerIds.has(player.player_id))
      .map(player => player.player_name)

    return winnerNames.length > 0 ? winnerNames.join(', ') : '—'
  }

  deleteCurrentGame() {
    const gameId = this.newGameId()
    if (!gameId) return
    this.confirmAndDeleteGame(gameId, () => this.closeWizard())
  }

  deleteSelectedGame() {
    const gameId = this.selectedGame?.game_id
    if (!gameId) return
    this.confirmAndDeleteGame(gameId, () => {
      this.showGameRoundsDialog.nativeElement.close()
      this.completedActionsMenuOpen.set(false)
      this.editingSelectedGameName.set(false)
      this.selectedGame = null
      this.refreshGames()
    })
  }

  toggleGameStatus(game: Game, event: Event) {
    event.stopPropagation()
    if (!this.authService.isAuthenticated()) return
    this.gamesService.setGameStatus(game.game_id, !game.is_completed).subscribe(() => {
      this.refreshGames()
    })
  }

  private confirmAndDeleteGame(gameId: number, onSuccess: () => void) {
    if (!confirm('Delete this game? This will permanently remove all of its rounds and scores.')) return
    this.gamesService.deleteGame(gameId).subscribe(onSuccess)
  }

  selectGame(game: Game) {
    this.selectedGame = game
    if (game.is_completed) {
      this.showDialogModal(this.showGameRoundsDialog.nativeElement)
    } else {
      this.resumeGame(game)
    }
  }

  resumeGame(game: Game) {
    const players = game.Players_X_Games.map(pxg => pxg.Players)

    this.newGamePlayers.set(players)
    this.newGameId.set(game.game_id)
    this.newGameDatetime.set(game.game_datetime)
    this.newGameName.set(game.game_name)
    this.refreshWizardRoundState(game)
    this.resetRoundForm()
    this.step.set('rounds')
    this.showDialogModal(this.gameWizardDialog.nativeElement)
    this.gameRealtime.connect(game.game_id)
  }

  private refreshWizardRoundState(game: Game) {
    const sortedRounds = [...game.Rounds].sort((a, b) => a.round_number - b.round_number)
    this.roundHistory.set(sortedRounds.map(r => this.toHistoryEntry(r)))
    const maxRoundNumber = sortedRounds.reduce((max, r) => Math.max(max, r.round_number), 0)
    this.currentRoundNumber.set(maxRoundNumber + 1)
  }

  startNewGame() {
    this.step.set('players')
    this.newGamePlayers.set([])
    this.newPlayerName.set('')
    this.addPlayerFormOpen.set(false)
    this.playerSearchQuery.set('')
    this.showPlayerDropdown.set(false)
    this.newGameId.set(null)
    this.newGameDatetime.set(null)
    this.newGameName.set(null)
    this.currentRoundNumber.set(1)
    this.roundHistory.set([])
    this.resetRoundForm()
    this.gamesService.getPlayers().subscribe(players => {
      this.existingPlayers.set(players)
    })
    this.showDialogModal(this.gameWizardDialog.nativeElement)
  }

  addExistingPlayer(player: Player) {
    const current = this.newGamePlayers()
    if (!current.find(p => p.player_id === player.player_id)) {
      this.newGamePlayers.set([...current, player])
    }
  }

  selectExistingPlayer(player: Player) {
    this.addExistingPlayer(player)
    this.playerSearchQuery.set('')
  }

  onPlayerSearchBlur() {
    setTimeout(() => this.showPlayerDropdown.set(false), 100)
  }

  handleAddPlayerClick() {
    if (this.addPlayerFormOpen()) {
      this.addNewPlayer()
    } else {
      this.addPlayerFormOpen.set(true)
    }
  }

  addNewPlayer() {
    const name = this.newPlayerName().trim()
    if (!name) return
    this.gamesService.createPlayer(name).subscribe(player => {
      const current = this.newGamePlayers()
      this.newGamePlayers.set([...current, player])
      this.newPlayerName.set('')
    })
  }

  removePlayer(index: number) {
    const current = this.newGamePlayers()
    current.splice(index, 1)
    this.newGamePlayers.set([...current])
  }

  submitGame() {
    const players = this.newGamePlayers()
    if (!this.isValidPlayerCount()) return
    this.gamesService.createGame({
      num_players: players.length,
      player_ids: players.map(p => p.player_id)
    }).subscribe(game => {
      this.newGameId.set(game.game_id)
      this.newGameDatetime.set(game.game_datetime)
      this.newGameName.set(game.game_name)
      this.step.set('rounds')
      this.resetRoundForm()
    })
  }

  calculatePlayerScores(): PlayerRoundScore[] {
    const allPlayers = this.newGamePlayers()
    const dealerId = this.isDealerGame() ? this.roundDealerPlayerId() : null
    if (this.isDealerGame() && !dealerId) return []
    const players = dealerId ? allPlayers.filter(p => p.player_id !== dealerId) : allPlayers
    const pickerId = this.roundPickerPlayerId()
    const partnerId = this.roundPartnerPlayerId()
    const result = this.roundResult()
    const isLeaster = result === 'Leaster'
    const numPlayers = players.length
    if (!pickerId || !result) return []

    const hasPartner = !isLeaster && !!partnerId
    const opponentDelta = 1
    const numOpponents = numPlayers - 1 - (hasPartner ? 1 : 0)
    const pickerDelta = hasPartner ? 2 : numOpponents * opponentDelta
    const partnerDelta = hasPartner ? 1 : null
    const leasterWinnerDelta = numPlayers === 3 ? 2 : 4
    const leasterLoserDelta = 1

    let multiplier = 1
    if (!isLeaster) {
      if (this.roundNoTrick()) multiplier = 3
      else if (this.roundNoSchneider()) multiplier = 2
    }

    const scores: PlayerRoundScore[] = players.map(player => {
      let role: PlayerRole
      let delta: number

      if (isLeaster) {
        if (player.player_id === pickerId) {
          role = 'Leaster Winner'
          delta = leasterWinnerDelta
        } else {
          role = 'Leaster Loser'
          delta = leasterLoserDelta
        }
      } else {
        if (player.player_id === pickerId) {
          role = 'Picker'
          delta = pickerDelta
        } else if (partnerId && player.player_id === partnerId) {
          role = 'Partner'
          delta = partnerDelta!
        } else {
          role = 'Opponent'
          delta = opponentDelta
        }
      }

      delta *= multiplier

      if (isLeaster) {
        if (role !== 'Leaster Winner') delta = -delta
      } else if (result === 'Picker Loss') {
        if (role === 'Picker' || role === 'Partner') delta = -delta
      } else {
        if (role === 'Opponent') delta = -delta
      }

      return { player_id: player.player_id, player_role: role, point_delta: delta }
    })

    if (dealerId) scores.push({ player_id: dealerId, player_role: 'Dealer', point_delta: 0 })
    return scores
  }

  submitRound() {
    const gameId = this.newGameId()
    const pickerId = this.roundPickerPlayerId()
    const result = this.roundResult()
    if (!gameId || !pickerId || !result) return
    if (this.isDealerGame() && !this.roundDealerPlayerId()) return

    const scores = this.roundPlayerScores()
    const editingId = this.editingRoundId()
    const noSchneider = this.roundNoSchneider()
    const noPartner = result === 'Leaster' ? false : this.roundNoPartner()
    const noTrick = this.roundNoTrick()

    this.isSubmittingRound.set(true)

    if (editingId) {
      this.gamesService.updateRound(editingId, {
        round_result: result,
        no_schneider: noSchneider,
        no_partner: noPartner,
        no_trick: noTrick,
        player_scores: scores
      }).subscribe(() => {
        this.roundHistory.update(h => h.map(entry => entry.round_id === editingId
          ? { ...entry, round_result: result, no_schneider: noSchneider, no_partner: noPartner, no_trick: noTrick, scores }
          : entry
        ))
        this.resetRoundForm()
      })
    } else {
      const roundNumber = this.currentRoundNumber()
      this.gamesService.createRound({
        game_id: gameId,
        round_number: roundNumber,
        round_result: result,
        no_schneider: noSchneider,
        no_partner: noPartner,
        no_trick: noTrick,
        player_scores: scores
      }).subscribe(created => {
        this.roundHistory.update(h => [...h, {
          round_id: created.round_id,
          round_number: roundNumber,
          round_result: result,
          no_schneider: noSchneider,
          no_partner: noPartner,
          no_trick: noTrick,
          scores
        }])
        this.currentRoundNumber.update(n => n + 1)
        this.resetRoundForm()
      })
    }
  }

  editRound(entry: RoundHistoryEntry) {
    const isLeaster = entry.round_result === 'Leaster'
    const pickerScore = entry.scores.find(s => s.player_role === (isLeaster ? 'Leaster Winner' : 'Picker'))
    const partnerScore = entry.scores.find(s => s.player_role === 'Partner')
    const dealerScore = entry.scores.find(s => s.player_role === 'Dealer')

    this.roundDealerPlayerId.set(dealerScore?.player_id ?? null)
    this.roundPickerPlayerId.set(pickerScore?.player_id ?? null)
    this.roundPartnerPlayerId.set(partnerScore?.player_id ?? null)
    this.roundResult.set(entry.round_result)
    this.roundNoSchneider.set(entry.no_schneider)
    this.roundNoPartner.set(entry.no_partner)
    this.roundNoTrick.set(entry.no_trick)
    this.editingRoundId.set(entry.round_id)
    this.addRoundFormOpen.set(true)
  }

  cancelEditRound() {
    this.resetRoundForm()
  }

  cancelAddRound() {
    this.resetRoundForm()
  }

  deleteRoundEntry(entry: RoundHistoryEntry) {
    if (!confirm(`Delete Round ${entry.round_number}? This cannot be undone.`)) return
    const gameId = this.newGameId()
    this.gamesService.deleteRound(entry.round_id).subscribe(() => {
      if (this.editingRoundId() === entry.round_id) this.resetRoundForm()
      if (!gameId) return
      this.gamesService.getGames().subscribe(games => {
        this.gamesSignal.set(games)
        const updatedGame = games.find(g => g.game_id === gameId)
        if (updatedGame) this.refreshWizardRoundState(updatedGame)
      })
    })
  }

  finishGame() {
    const gameId = this.newGameId()
    if (!gameId) return
    if (!confirm('Finish this game? You can still reopen it later by tapping its status badge.')) return
    this.gamesService.completeGame(gameId).subscribe(() => {
      this.closeWizard()
    })
  }

  closeWizard() {
    this.refreshGames()
    this.gameWizardDialog.nativeElement.close()
    this.step.set('idle')
    this.roundActionsMenuOpen.set(false)
    this.editingGameName.set(false)
    this.gameRealtime.disconnect()
  }

  startEditGameName() {
    if (!this.authService.isAuthenticated()) return
    this.gameNameInput.set(this.newGameName() ?? '')
    this.editingGameName.set(true)
  }

  saveGameName() {
    const gameId = this.newGameId()
    this.editingGameName.set(false)
    if (!gameId) return
    const newName = this.gameNameInput().trim() || null
    const previousName = this.newGameName()
    if (newName === previousName) return
    this.newGameName.set(newName)
    this.gamesService.setGameName(gameId, newName).subscribe({
      next: updated => {
        this.newGameName.set(updated.game_name)
        this.refreshGames()
      },
      error: () => {
        this.newGameName.set(previousName)
      }
    })
  }

  cancelEditGameName() {
    this.editingGameName.set(false)
  }

  startEditSelectedGameName() {
    if (!this.authService.isAuthenticated() || !this.selectedGame) return
    this.selectedGameNameInput.set(this.selectedGame.game_name ?? '')
    this.editingSelectedGameName.set(true)
  }

  saveSelectedGameName() {
    this.editingSelectedGameName.set(false)
    if (!this.selectedGame) return
    const gameId = this.selectedGame.game_id
    const newName = this.selectedGameNameInput().trim() || null
    const previousName = this.selectedGame.game_name
    if (newName === previousName) return
    this.selectedGame.game_name = newName
    this.gamesService.setGameName(gameId, newName).subscribe({
      next: updated => {
        if (this.selectedGame) this.selectedGame.game_name = updated.game_name
        this.refreshGames()
      },
      error: () => {
        if (this.selectedGame) this.selectedGame.game_name = previousName
      }
    })
  }

  cancelEditSelectedGameName() {
    this.editingSelectedGameName.set(false)
  }

  toggleRoundActionsMenu() {
    this.roundActionsMenuOpen.set(!this.roundActionsMenuOpen())
  }

  onGameRoundsBackdropClick(event: MouseEvent) {
    if (event.target !== event.currentTarget) return
    this.closeGameRoundsDialog()
  }

  closeGameRoundsDialog() {
    this.showGameRoundsDialog.nativeElement.close()
    this.completedActionsMenuOpen.set(false)
    this.editingSelectedGameName.set(false)
  }

  toggleCompletedActionsMenu() {
    this.completedActionsMenuOpen.set(!this.completedActionsMenuOpen())
  }

  scrollFieldIntoView(event: FocusEvent) {
    (event.target as HTMLElement).scrollIntoView({ block: 'center', behavior: 'smooth' })
  }

  onWizardBackdropClick(event: MouseEvent) {
    if (event.target !== event.currentTarget) return
    if (this.step() === 'rounds') {
      this.closeWizard()
    } else {
      this.gameWizardDialog.nativeElement.close()
      this.step.set('idle')
    }
  }

  onPickerChange(playerId: number | null) {
    this.roundPickerPlayerId.set(playerId)
    this.roundPartnerPlayerId.set(null)
    this.roundNoPartner.set(this.defaultNoPartner())
  }

  onDealerChange(playerId: number | null) {
    this.roundDealerPlayerId.set(playerId)
    this.roundPickerPlayerId.set(null)
    this.roundPartnerPlayerId.set(null)
    this.roundResult.set('')
    this.roundNoSchneider.set(false)
    this.roundNoTrick.set(false)
  }

  onPartnerChange(value: number | null) {
    if (value === -1) {
      this.roundNoPartner.set(true)
      this.roundPartnerPlayerId.set(null)
    } else {
      this.roundNoPartner.set(false)
      this.roundPartnerPlayerId.set(value)
    }
  }

  toggleNoSchneider(value: boolean) {
    this.roundNoSchneider.set(value)
    if (!value) this.roundNoTrick.set(false)
  }

  availablePlayers(): Player[] {
    const selectedIds = new Set(this.newGamePlayers().map(p => p.player_id))
    return this.existingPlayers().filter(p => !selectedIds.has(p.player_id))
  }

  filteredAvailablePlayers(): Player[] {
    const query = this.playerSearchQuery().trim().toLowerCase()
    const available = this.availablePlayers()
    if (!query) return available
    return available.filter(p => p.player_name.toLowerCase().includes(query))
  }

  getPlayerName(playerId: number): string {
    return this.newGamePlayers().find(p => p.player_id === playerId)?.player_name ?? ''
  }

  roleClass(role: string): string {
    return 'role--' + role.replace(/\s+/g, '_')
  }

  absScore(value: number | undefined): number {
    return Math.abs(value ?? 0)
  }

  formatGameDateTime(isoDateTime: string): string {
    const normalized = this.normalizeDatetime(isoDateTime)
    const datePart = formatDate(normalized, 'EEE MMM d, y', 'en-US')
    const timePart = formatDate(normalized, 'h:mm a', 'en-US').replace(' ', '').toLowerCase()
    return `${datePart}: ${timePart}`
  }

  formatShortGameDateTime(isoDateTime: string): string {
    const normalized = this.normalizeDatetime(isoDateTime)
    const month = formatDate(normalized, 'MMM', 'en-US')
    const dayYear = formatDate(normalized, 'd, y', 'en-US')
    const timePart = formatDate(normalized, 'h:mm a', 'en-US').replace(' ', '').toLowerCase()
    return `${month}. ${dayYear} ${timePart}`
  }

  normalizeDatetime(isoDateTime: string): string {
    return /Z$|[+-]\d{2}:\d{2}$/.test(isoDateTime) ? isoDateTime : isoDateTime + 'Z'
  }

  getSelectedGamePlayers(): Player[] {
    return this.selectedGame?.Players_X_Games.map(pxg => pxg.Players) ?? []
  }

  getSelectedGameRounds(): Round[] {
    return [...(this.selectedGame?.Rounds ?? [])].sort((a, b) => a.round_number - b.round_number)
  }

  selectedGameScoreTable(): ScoreTable {
    if (!this.selectedGame) return { players: [], initials: new Map(), rows: [], winnerIds: new Set() }
    const roundsData = this.selectedGame.Rounds.map(r => this.toHistoryEntry(r))
    return this.buildScoreTable(this.getSelectedGamePlayers(), roundsData, this.selectedGame.is_completed)
  }

  private toHistoryEntry(round: Round): RoundHistoryEntry {
    return {
      round_id: round.round_id,
      round_number: round.round_number,
      round_result: round.round_result,
      no_schneider: round.no_schneider,
      no_partner: round.no_partner,
      no_trick: round.no_trick,
      scores: round.PlayerRoundScore.map(s => ({ player_id: s.player_id, player_role: s.player_role, point_delta: s.point_delta }))
    }
  }

  private resetRoundForm() {
    this.roundPickerPlayerId.set(null)
    this.roundPartnerPlayerId.set(null)
    this.roundResult.set('')
    this.roundNoSchneider.set(false)
    this.roundNoPartner.set(this.defaultNoPartner())
    this.roundNoTrick.set(false)
    this.roundDealerPlayerId.set(null)
    this.editingRoundId.set(null)
    this.isSubmittingRound.set(false)
    this.addRoundFormOpen.set(false)
  }

  private defaultNoPartner(): boolean {
    return this.newGamePlayers().length === 5
  }

  private buildScoreTable(players: Player[], roundsData: RoundHistoryEntry[], highlightWinner = false): ScoreTable {
    const sortedPlayers = this.sortPlayersByInitials(players)
    const sortedRounds = [...roundsData].sort((a, b) => a.round_number - b.round_number)
    const runningTotals = new Map<number, number>(sortedPlayers.map(p => [p.player_id, 0]))

    const rows: ScoreTableRow[] = sortedRounds.map(round => {
      for (const score of round.scores) {
        runningTotals.set(score.player_id, (runningTotals.get(score.player_id) ?? 0) + score.point_delta)
      }
      const pickerId = round.scores.find(s => s.player_role === 'Picker')?.player_id ?? null
      const partnerId = round.scores.find(s => s.player_role === 'Partner')?.player_id ?? null
      const dealerId = round.scores.find(s => s.player_role === 'Dealer')?.player_id ?? null
      return { round_number: round.round_number, totals: new Map(runningTotals), pickerId, partnerId, dealerId }
    })

    const lastRow = rows[rows.length - 1]
    const winnerIds = new Set<number>()
    if (highlightWinner && lastRow) {
      const highestTotal = Math.max(...lastRow.totals.values())
      for (const [playerId, total] of lastRow.totals) {
        if (total === highestTotal) winnerIds.add(playerId)
      }
    }

    return { players: sortedPlayers, initials: this.computePlayerInitials(sortedPlayers), rows, winnerIds }
  }

  activeInitialsTooltip = signal<number | null>(null)

  toggleInitialsTooltip(playerId: number, event: Event): void {
    event.stopPropagation()
    this.activeInitialsTooltip.set(this.activeInitialsTooltip() === playerId ? null : playerId)
  }

  @HostListener('document:click')
  closeInitialsTooltip(): void {
    this.activeInitialsTooltip.set(null)
  }

  private sortPlayersByInitials(players: Player[]): Player[] {
    return [...players].sort((a, b) => {
      const initialsCompare = this.getEffectiveInitials(a).localeCompare(this.getEffectiveInitials(b))
      return initialsCompare !== 0 ? initialsCompare : a.player_name.localeCompare(b.player_name)
    })
  }

  private computePlayerInitials(players: Player[]): Map<number, string> {
    const baseInitials = players.map(p => this.getEffectiveInitials(p))
    const totalCounts = new Map<string, number>()
    for (const initials of baseInitials) {
      totalCounts.set(initials, (totalCounts.get(initials) ?? 0) + 1)
    }

    const seenCounts = new Map<string, number>()
    const result = new Map<number, string>()
    players.forEach((player, i) => {
      const initials = baseInitials[i]
      if ((totalCounts.get(initials) ?? 0) > 1) {
        const occurrence = (seenCounts.get(initials) ?? 0) + 1
        seenCounts.set(initials, occurrence)
        result.set(player.player_id, `${initials}${occurrence}`)
      } else {
        result.set(player.player_id, initials)
      }
    })
    return result
  }

  private getEffectiveInitials(player: Player): string {
    return player.scoreboard_initials ?? this.getBaseInitials(player.player_name)
  }

  scoreboardColor(player: Player): string {
    return player.scoreboard_color ?? '#1A1A2E'
  }

  scoreboardTextColor(player: Player): '#000000' | '#FFFFFF' {
    const color = this.scoreboardColor(player)
    const red = parseInt(color.slice(1, 3), 16) / 255
    const green = parseInt(color.slice(3, 5), 16) / 255
    const blue = parseInt(color.slice(5, 7), 16) / 255
    const linear = [red, green, blue].map(channel => (
      channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4)
    ))
    const luminance = (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2])
    return luminance > 0.179 ? '#000000' : '#FFFFFF'
  }

  private getBaseInitials(name: string): string {
    const tokens = name.trim().split(/\s+/).filter(Boolean)
    if (tokens.length === 0) return '??'
    if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase()
    return (tokens[0][0] + tokens[tokens.length - 1][0]).toUpperCase()
  }
}
