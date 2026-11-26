// apps/miniapp/src/components/dayAccess.ts — доступ к дню (miniapp-pause-c3a §7.4, регрессия 4 t5-bc §4).
// Чистые функции: без таймеров и без React; время приходит аргументом nowMs.
// День допускает только свежий GET: из error никакое время не даёт open без нового checkDayAccess.
// requested и approved дают open: статус дня решает GET /day/current, клиент даты и окно не считает.
// В main модуль никто не вызывает (DayGuard и экран /paused — c3b).

import { ApiError, type PauseStatus } from '../api/client.ts';
import { PAUSE_STATUS_ACTIVE } from './pause.ts';

export type DayAccess =
  | { kind: 'open' }
  | { kind: 'paused' }
  | { kind: 'error'; error: unknown; retryAt: number };

/** ApiError 429 с retryAfter → nowMs + retryAfter × 1000; иначе nowMs. */
export function retryAtFrom(err: unknown, nowMs: number): number {
  if (err instanceof ApiError && err.status === 429 && err.retryAfter !== null) {
    return nowMs + err.retryAfter * 1000;
  }
  return nowMs;
}

/** Только для kind 'error': true при nowMs >= retryAt. */
export function canRetry(access: DayAccess, nowMs: number): boolean {
  return access.kind === 'error' && nowMs >= access.retryAt;
}

/** Ровно один вызов get() (в c3b это getPause). */
export async function checkDayAccess(get: () => Promise<PauseStatus>, nowMs: number): Promise<DayAccess> {
  let status: PauseStatus;
  try {
    status = await get();
  } catch (error) {
    return { kind: 'error', error, retryAt: retryAtFrom(error, nowMs) };
  }
  return status.pause?.status === PAUSE_STATUS_ACTIVE ? { kind: 'paused' } : { kind: 'open' };
}
