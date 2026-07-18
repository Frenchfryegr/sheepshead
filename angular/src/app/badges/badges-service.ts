import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Badge } from '../interfaces/badge';

@Injectable({
  providedIn: 'root',
})
export class BadgesService {
  private http = inject(HttpClient)

  getBadges(): Observable<Badge[]> {
    return this.http.get<Badge[]>(`${environment.apiUrl}/${environment.badges}`)
  }
}
