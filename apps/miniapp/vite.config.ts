/// <reference types="vitest/config" />
// apps/miniapp/vite.config.ts
// Основа — официальный шаблон @telegram-apps/create-mini-app (reactjs-template).
// Убраны: base '/reactjs-template/' (GitHub Pages), mkcert, terser.
//
// Никаких хардкодов адресов: всё берётся из переменных окружения.
//   VITE_API_BASE_URL   — базовый URL API для клиента (build-time). Пусто = тот же origin,
//                         что требует CSP E2 (connect-src 'self').
//   VITE_DEV_API_PROXY  — ТОЛЬКО для `npm run dev`: куда проксировать /miniapp/v1 и /healthz
//                         (например, адрес API на dev-машине). Пусто = прокси выключен.
// Dev-сервер слушает 127.0.0.1:5173 (см. scripts.dev в package.json, правило IRONCLAD).
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const devApiProxy = env.VITE_DEV_API_PROXY;

  return {
    plugins: [react(), tsconfigPaths()],
    build: {
      target: 'es2022',
      // Без eval-подобных sourcemap в prod: CSP E2 запрещает 'unsafe-eval'.
      sourcemap: false,
    },
    publicDir: './public',
    server: devApiProxy
      ? {
          proxy: {
            '/miniapp/v1': { target: devApiProxy, changeOrigin: true },
            '/healthz': { target: devApiProxy, changeOrigin: true },
          },
        }
      : undefined,
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts'],
    },
  };
});
