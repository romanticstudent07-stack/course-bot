// apps/miniapp/src/index.tsx — точка входа Mini App.
// Основа — шаблон @telegram-apps/create-mini-app (reactjs-template, TypeScript).
import ReactDOM from 'react-dom/client';
import { StrictMode } from 'react';
import { retrieveLaunchParams } from '@telegram-apps/sdk-react';

import { Root } from '@/components/Root.tsx';
import { EnvUnsupported } from '@/components/EnvUnsupported.tsx';
import { init } from '@/init.ts';

import './index.css';

// Мок окружения Telegram — ТОЛЬКО в dev-режиме Vite (tree-shaking вырезает из prod-бандла).
import './mockEnv.ts';

const root = ReactDOM.createRoot(document.getElementById('root')!);

try {
  const launchParams = retrieveLaunchParams();
  const debug = (launchParams.tgWebAppStartParam || '').includes('debug') || import.meta.env.DEV;

  init({ debug });
  root.render(
    <StrictMode>
      <Root/>
    </StrictMode>,
  );
} catch {
  // Не внутри Telegram (или слишком старый клиент) — показываем заглушку.
  root.render(<EnvUnsupported/>);
}
