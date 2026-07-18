import { inject, Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Badge } from '../interfaces/badge';

@Injectable({
  providedIn: 'root',
})
export class BadgesService {
  private http = inject(HttpClient)

  // Held here (not in the Badges/Profile components) so the last-known list survives
  // those components being destroyed and recreated on route navigation.
  private badgesSignal = signal<Badge[]>([])
  badges = this.badgesSignal.asReadonly()

  setBadges(badges: Badge[]): void {
    this.badgesSignal.set(badges)
  }

  getBadges(): Observable<Badge[]> {
    return this.http.get<Badge[]>(`${environment.apiUrl}/${environment.badges}`)
  }
}
