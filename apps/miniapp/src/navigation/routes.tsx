import type { ComponentType } from 'react';

import { DayPage } from '@/pages/DayPage/DayPage.tsx';

interface Route {
  path: string;
  Component: ComponentType;
}

// '/' занят onb.welcome (miniapp-screens.md); экран текущего дня — /day (day.current).
// HomePage.tsx оставлен в репозитории, но в маршрутах не используется.
export const routes: Route[] = [
  { path: '/day', Component: DayPage },
];
