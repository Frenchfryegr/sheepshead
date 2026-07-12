import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { GamesService } from '../games-service';
import { Game } from '../../interfaces/game';

@Component({
  selector: 'app-games',
  standalone: false,
  templateUrl: './games.html',
  styleUrl: './games.css',
})
export class Games {
  private gamesService = inject(GamesService)

  games = toSignal(this.gamesService.getGames(), { initialValue: [] });  selectedGame: Game | null = null

  addGame() {

  }

selectGame(game_id: number) {
  this.selectedGame = this.games()?.find(game => game.game_id === game_id) ?? null;
  console.log("selected game " + game_id)
  console.log(this.selectedGame)
}

  // getRoundsForGame(game_id: number) {
  //   this.selectedGame = toSignal(this.gamesService.getRoundsForGame(game_id))
  // }
}
