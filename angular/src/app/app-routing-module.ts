import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';

import { profileGuard } from './auth/profile.guard';
import { Games } from './games/games/games';
import { Profile } from './profile/profile';
import { Badges } from './badges/badges';
import { Achievements } from './achievements/achievements';

const routes: Routes = [
  { path: '', component: Games },
  { path: 'profile', component: Profile, canActivate: [profileGuard] },
  { path: 'badges', component: Badges },
  { path: 'achievements', component: Achievements },
  { path: '**', redirectTo: '' },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule],
})
export class AppRoutingModule {}
