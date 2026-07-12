import { platformBrowser } from '@angular/platform-browser';
import { AppModule } from './app/app-module';

platformBrowser()
  .bootstrapModule(AppModule, {})
  .then(() => {
    const splash = document.getElementById('app-splash');
    if (!splash) return;
    splash.style.transition = 'opacity 0.3s ease';
    splash.style.opacity = '0';
    setTimeout(() => splash.remove(), 300);
  })
  .catch((err) => console.error(err));
