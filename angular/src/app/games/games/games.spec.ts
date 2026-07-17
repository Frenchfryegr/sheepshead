import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FormsModule } from '@angular/forms';
import { of, Subject } from 'rxjs';

import { Games } from './games';
import { AuthService } from '../../auth/auth-service';
import { GameRealtimeService } from '../game-realtime-service';
import { GamesService } from '../games-service';

describe('Games', () => {
  let component: Games;
  let fixture: ComponentFixture<Games>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [Games],
      imports: [FormsModule],
      providers: [
        {
          provide: GamesService,
          useValue: {
            getGames: () => of([]),
            getPlayers: () => of([]),
          },
        },
        {
          provide: GameRealtimeService,
          useValue: {
            updates: new Subject<void>(),
            listUpdates: new Subject<void>(),
            connectList: () => undefined,
          },
        },
        {
          provide: AuthService,
          useValue: {
            isAuthenticated: () => false,
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(Games);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('uses fallback scoreboard colors and contrast', () => {
    const player = { player_id: 1, player_name: 'Caleb Frye', scoreboard_initials: null, scoreboard_color: null, scoreboard_avatar_url: null };

    expect(component.scoreboardColor(player)).toBe('#1A1A2E');
    expect(component.scoreboardTextColor(player)).toBe('#FFFFFF');
  });

  it('uses black text on light scoreboard colors', () => {
    const player = { player_id: 1, player_name: 'Caleb Frye', scoreboard_initials: null, scoreboard_color: '#FFFFFF', scoreboard_avatar_url: null };

    expect(component.scoreboardTextColor(player)).toBe('#000000');
  });

  it('deduplicates effective initials from profile preferences', () => {
    const table = (component as unknown as {
      buildScoreTable: (players: unknown[], roundsData: unknown[]) => { initials: Map<number, string> }
    }).buildScoreTable([
      { player_id: 1, player_name: 'Caleb Frye', scoreboard_initials: 'CF', scoreboard_color: null, scoreboard_avatar_url: null },
      { player_id: 2, player_name: 'Chris Fox', scoreboard_initials: 'CF', scoreboard_color: null, scoreboard_avatar_url: null },
    ], []);

    expect(table.initials.get(1)).toBe('CF1');
    expect(table.initials.get(2)).toBe('CF2');
  });
});
