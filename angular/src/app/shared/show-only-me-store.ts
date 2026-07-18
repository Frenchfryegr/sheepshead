import { Injectable, signal } from '@angular/core';

// Shared "Show only me" state for the badges / achievements / statistics pages.
// Held in a root singleton so the choice persists while navigating between those pages,
// but resets to the default (on) on a full page reload (the service is recreated then).
// A ?showOnlyMe=true|false query param still overrides it on page load — see each page's
// ngOnInit — so a big-screen URL can pin the state across reloads.
@Injectable({
  providedIn: 'root',
})
export class ShowOnlyMeStore {
  private state = signal(true)
  value = this.state.asReadonly()

  set(showOnlyMe: boolean): void {
    this.state.set(showOnlyMe)
  }
}
