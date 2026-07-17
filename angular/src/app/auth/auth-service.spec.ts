import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';

import { environment } from '../../environments/environment';
import { AuthService } from './auth-service';
import { TokenStore } from './token-store';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;
  let tokenStore: TokenStore;

  const profile = {
    username: 'Caleb',
    contact_email: 'caleb@example.com',
    avatar_url: 'https://example.com/avatar.png',
    scoreboard_initials: 'CF',
    scoreboard_color: '#667EEA',
    show_avatar_on_scoreboard: true,
    claimed_player_id: 12,
    claimed_player_name: 'Caleb Frye',
  }

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    tokenStore = TestBed.inject(TokenStore);
  });

  afterEach(() => {
    httpMock.verify();
    tokenStore.clear();
  });

  it('updates account state after loading the profile', () => {
    service.getProfile().subscribe(result => expect(result).toEqual(profile));

    const req = httpMock.expectOne(`${environment.apiUrl}/${environment.auth}/profile`);
    expect(req.request.method).toBe('GET');
    req.flush(profile);

    expect(service.username()).toBe('Caleb');
    expect(service.contactEmail()).toBe('caleb@example.com');
    expect(service.avatarUrl()).toBe('https://example.com/avatar.png');
    expect(service.scoreboardInitials()).toBe('CF');
    expect(service.scoreboardColor()).toBe('#667EEA');
    expect(service.showAvatarOnScoreboard()).toBe(true);
  });

  it('sends profile patches to the profile endpoint', () => {
    const update = { username: 'CalebF', contact_email: null, scoreboard_initials: 'CF', scoreboard_color: '#667EEA', show_avatar_on_scoreboard: true };

    service.updateProfile(update).subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/${environment.auth}/profile`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual(update);
    req.flush({ ...profile, username: 'CalebF', contact_email: null });
  });

  it('uploads profile pictures with multipart form data', () => {
    const file = new File(['abc'], 'avatar.png', { type: 'image/png' });

    service.uploadProfilePicture(file).subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/${environment.auth}/profile/picture`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body instanceof FormData).toBe(true);
    expect(req.request.body.get('file')).toBe(file);
    req.flush(profile);
  });
});
