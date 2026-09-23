/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Базовый URL API. Пусто — тот же origin (CSP E2: connect-src 'self'). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
