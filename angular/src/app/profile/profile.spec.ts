import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { of } from 'rxjs';

import { AuthService } from '../auth/auth-service';
import { Profile } from './profile';

describe('Profile', () => {
  let component: Profile;
  let fixture: ComponentFixture<Profile>;

  const profile = {
    username: 'Caleb',
    contact_email: 'caleb@example.com',
    avatar_url: null,
    scoreboard_initials: 'CF',
    scoreboard_color: '#667EEA',
    show_avatar_on_scoreboard: true,
    claimed_player_id: 1,
    claimed_player_name: 'Caleb Frye',
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [Profile],
      imports: [FormsModule],
      schemas: [NO_ERRORS_SCHEMA],
      providers: [
        {
          provide: AuthService,
          useValue: {
            getProfile: () => of(profile),
            updateProfile: () => of(profile),
            uploadProfilePicture: () => of(profile),
            deleteProfilePicture: () => of(profile),
          },
        },
        { provide: Router, useValue: { navigate: () => Promise.resolve(true) } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(Profile);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('loads editable profile fields', () => {
    expect(component.username()).toBe('Caleb');
    expect(component.contactEmail()).toBe('caleb@example.com');
    expect(component.scoreboardInitials()).toBe('CF');
    expect(component.scoreboardColor()).toBe('#667EEA');
    expect(component.showAvatarOnScoreboard()).toBe(true);
  });
});
