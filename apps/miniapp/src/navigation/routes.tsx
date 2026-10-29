import type { ComponentType } from 'react';

import { DayPage } from '@/pages/DayPage/DayPage.tsx';

interface Route {
  path: string;
  Component: ComponentType;
}

// '/' занят onb.welcome (miniapp-screens.md); экран текущего дня — /day (day.current).
export const routes: Route[] = [
  { path: '/day', Component: DayPage },
];
