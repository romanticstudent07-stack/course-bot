import type { ComponentType } from 'react';

import { HomePage } from '@/pages/HomePage/HomePage.tsx';

interface Route {
  path: string;
  Component: ComponentType;
}

// Экраны онбординга (onb.welcome → onb.age-gate → …) появятся в Итерации 1.
export const routes: Route[] = [
  { path: '/', Component: HomePage },
];
