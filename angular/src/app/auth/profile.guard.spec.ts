import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { AuthService } from './auth-service';
import { profileGuard } from './profile.guard';

describe('profileGuard', () => {
  function runGuard() {
    return TestBed.runInInjectionContext(() => profileGuard({} as never, {} as never))
  }

  it('allows authenticated users', () => {
    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: { isAuthenticated: () => true } },
        { provide: Router, useValue: { createUrlTree: () => ({}) } },
      ],
    })

    expect(runGuard()).toBe(true)
  })

  it('redirects logged-out users to games', () => {
    const urlTree = {}
    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: { isAuthenticated: () => false } },
        { provide: Router, useValue: { createUrlTree: () => urlTree } },
      ],
    })

    expect(runGuard()).toBe(urlTree)
  })
})
