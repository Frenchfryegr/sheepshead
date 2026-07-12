import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { FormsModule } from '@angular/forms';

import { Games } from './games';

describe('Games', () => {
  let component: Games;
  let fixture: ComponentFixture<Games>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [Games],
      imports: [HttpClientTestingModule, FormsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(Games);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
