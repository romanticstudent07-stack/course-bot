import type { ComponentType } from 'react';

import { DayPage } from '@/pages/DayPage/DayPage.tsx';
import { MeCardPage } from '@/pages/MePage/MeCardPage.tsx';
import { MeChangeMapPage } from '@/pages/MePage/MeChangeMapPage.tsx';
import { MeConsentsPage } from '@/pages/MePage/MeConsentsPage.tsx';
import { PausedPage } from '@/pages/PausedPage/PausedPage.tsx';

interface Route {
  path: string;
  Component: ComponentType;
}

// '/' занят onb.welcome (miniapp-screens.md); экран текущего дня — /day (day.current).
// /me — me.card (miniapp-screens.md)
// /me/consents — me.consents, /me/change-map — me.change-map (miniapp-i3-2b)
// /paused — lifecycle.paused (miniapp-pause-1); /returned не добавлять (карточка §13)
export const routes: Route[] = [
  { path: '/day', Component: DayPage },
  { path: '/me', Component: MeCardPage },
  { path: '/me/consents', Component: MeConsentsPage },
  { path: '/me/change-map', Component: MeChangeMapPage },
  { path: '/paused', Component: PausedPage },
];
