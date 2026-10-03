// apps/miniapp/src/api/client.ts — HTTP-клиент к backend (/miniapp/v1/**).
//
// Правила (AGENTS.md, miniapp-api-contract.yaml):
//   - на сервер уходит СЫРАЯ строка initData в заголовке X-Telegram-Init-Data;
//     initDataUnsafe для решений не используется;
//   - базовый URL — из VITE_API_BASE_URL (пусто = тот же origin, CSP E2 connect-src 'self');
//   - state-меняющие вызовы несут X-Client-Op-Id (uuid v4) — идемпотентность (D-17).
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

/**
 * tg_user_id из сырой строки initData — ТОЛЬКО для привязки локального черновика
 * к пользователю (drafts.ts: другой пользователь → полная очистка). Для решений
 * сервера не используется: сервер берёт tg_user_id из проверенной initData.
 */
export function tgUserIdFromInitData(raw: string | undefined): number | null {
  if (!raw) return null;
  try {
    const userRaw = new URLSearchParams(raw).get('user');
    if (!userRaw) return null;
    const user: unknown = JSON.parse(userRaw);
    if (typeof user !== 'object' || user === null) return null;
    const id = (user as { id?: unknown }).id;
    return typeof id === 'number' && Number.isSafeInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function readTgUserId(): number | null {
  return tgUserIdFromInitData(readInitData());
}

/** uuid v4 для X-Client-Op-Id (getRandomValues есть во всех webview, randomUUID — не везде). */
export function newClientOpId(): string {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
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
// UI: apps/miniapp/src/components/OnboardingFlow.tsx (до pid) и LaterSteps.tsx (после pid).

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

/** clientOpId — один на весь онбординг; повтор после ошибки уходит с тем же id (D-17). */
export const postFirstLaunch = (body: FirstLaunchRequest, clientOpId: string) =>
  apiRequest<PidCreated>('/miniapp/v1/onboarding/first-launch', { method: 'POST', body, clientOpId });

// ---- Согласия (1e-2): только чтение своих ----

export interface ConsentOut {
  id: ConsentId;
  given_at: string;
  revoked_at: string | null;
  legal_status: string;
}

export const getConsents = () => apiRequest<ConsentOut[]>('/miniapp/v1/consents');

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
