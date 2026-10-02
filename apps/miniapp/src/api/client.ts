// apps/miniapp/src/api/client.ts — HTTP-клиент к backend (/miniapp/v1/**).
//
// Правила (AGENTS.md, miniapp-api-contract.yaml):
//   - на сервер уходит СЫРАЯ строка initData в заголовке X-Telegram-Init-Data;
//     initDataUnsafe для решений не используется;
//   - базовый URL — из VITE_API_BASE_URL (пусто = тот же origin, CSP E2 connect-src 'self');
//   - state-меняющие вызовы несут X-Client-Op-Id (uuid v4) — идемпотентность.
import { retrieveRawInitData } from '@telegram-apps/sdk-react';

export const INIT_DATA_HEADER = 'X-Telegram-Init-Data';
export const CLIENT_OP_ID_HEADER = 'X-Client-Op-Id';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Нормализует базовый URL: без завершающего слэша; пусто — относительные пути. */
export function normalizeBaseUrl(raw: string | undefined): string {
  return (raw ?? '').trim().replace(/\/+$/, '');
}

export function buildUrl(baseUrl: string, path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizeBaseUrl(baseUrl)}${cleanPath}`;
}

function readInitData(): string | undefined {
  try {
    return retrieveRawInitData();
  } catch {
    return undefined;
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT';
  body?: unknown;
  clientOpId?: string;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const initData = readInitData();
  if (initData) headers[INIT_DATA_HEADER] = initData;
  if (options.clientOpId) headers[CLIENT_OP_ID_HEADER] = options.clientOpId;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(buildUrl(import.meta.env.VITE_API_BASE_URL ?? '', path), {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: 'same-origin',
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const err = (payload ?? {}) as { code?: string; message?: string };
    throw new ApiError(response.status, err.code ?? 'HTTP_ERROR', err.message ?? response.statusText);
  }
  return payload as T;
}

// ---- Онбординг (SEAM-1) — контракт build/miniapp-api-contract.yaml ----
// UI экранов онбординга — apps/miniapp/src/components/OnboardingFlow.tsx (1e-1b).

/** Единый реестр согласий C0–C6 (Consent.id в контракте). До pid обязательны C0 и C1. */
export type ConsentId = 'C0' | 'C1' | 'C2' | 'C3' | 'C4' | 'C5' | 'C6';

export interface FirstLaunchRequest {
  /** Дата рождения, ISO-8601 (YYYY-MM-DD). Возрастной гейт — на сервере (ADD3). */
  birth_date: string;
  /** Только id согласий; текст и его версию выбирает сервер (B-2, D-10). */
  consents: ConsentId[];
}

export interface PidCreated {
  pid: string;
  short_no: string;
}

export const postFirstLaunch = (body: FirstLaunchRequest) =>
  apiRequest<PidCreated>('/miniapp/v1/onboarding/first-launch', { method: 'POST', body });

// ---- Тексты (text_registry, 1d) ----

export interface TextOut {
  key: string;
  tone: string;
  legal_status: string;
  text: string;
  plurals_ru?: Record<string, string> | null;
}

export interface TextsBulkResponse {
  texts: TextOut[];
  /** Ключи, которых нет в реестре; клиент показывает нейтральную заглушку. */
  missing: string[];
}

export const postTextsBulk = (keys: string[]) =>
  apiRequest<TextsBulkResponse>('/miniapp/v1/texts/bulk', { method: 'POST', body: { keys } });
