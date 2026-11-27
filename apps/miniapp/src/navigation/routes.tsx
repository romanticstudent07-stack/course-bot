import type { ComponentType } from 'react';

import { DayGuard } from '@/components/DayGuard.tsx';
import { DayPage } from '@/pages/DayPage/DayPage.tsx';
import { MeCardPage } from '@/pages/MePage/MeCardPage.tsx';
import { MeChangeMapPage } from '@/pages/MePage/MeChangeMapPage.tsx';
import { MeConsentsPage } from '@/pages/MePage/MeConsentsPage.tsx';
import { PausedPage } from '@/pages/PausedPage/PausedPage.tsx';

interface Route {
  path: string;
  Component: ComponentType;
}

/** /day под DayGuard (miniapp-pause-c3b §7.1): день открывается только после свежего GET /pause. */
function GuardedDayPage() {
  return (
    <DayGuard>
      <DayPage/>
    </DayGuard>
  );
}

// '/' занят onb.welcome (miniapp-screens.md); экран текущего дня — /day (day.current).
// /day — DayPage внутри DayGuard; /paused — экран паузы PausedPage (lifecycle.paused, c3b-2).
// /me — me.card (miniapp-screens.md)
// /me/consents — me.consents, /me/change-map — me.change-map (miniapp-i3-2b)
export const routes: Route[] = [
  { path: '/day', Component: GuardedDayPage },
  { path: '/paused', Component: PausedPage },
  { path: '/me', Component: MeCardPage },
  { path: '/me/consents', Component: MeConsentsPage },
  { path: '/me/change-map', Component: MeChangeMapPage },
];
