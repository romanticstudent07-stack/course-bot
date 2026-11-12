import type { ComponentType } from 'react';

import { DayPage } from '@/pages/DayPage/DayPage.tsx';
import { MeCardPage } from '@/pages/MePage/MeCardPage.tsx';

interface Route {
  path: string;
  Component: ComponentType;
}

// '/' занят onb.welcome (miniapp-screens.md); экран текущего дня — /day (day.current).
// /me — me.card (miniapp-screens.md)
export const routes: Route[] = [
  { path: '/day', Component: DayPage },
  { path: '/me', Component: MeCardPage },
];
