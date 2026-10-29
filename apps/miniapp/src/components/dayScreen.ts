// apps/miniapp/src/components/dayScreen.ts — чистые функции экрана /day (day-screen-a), без React.
//
// «Какой экран» — только status ответа GET /miniapp/v1/day/current; «можно ли нажать» — только
// buttons_active. Окно 04:00–00:00 клиент не считает. Дату и время для показа берём из строки
// сервера (wallClock), не через new Date() в поясе телефона. «Сейчас» приходит аргументом nowMs.
// miniapp-fix-2: dayRetryDelayMs — повтор GET /day/current только после 503 SERVICE_UNAVAILABLE.
import { ApiError, type DayCurrent } from '../api/client.ts';
import { errorMessage } from './OnboardingFlow.tsx';

export const DAY_TEXT_KEYS = {
  activeFromHint: 'B9.day_active_from_hint',
  queueWait: 'B9.day_queue_wait',
  closedHint: 'B9.day_closed_hint',
} as const;

export type DayView =
  | 'not_started'
  | 'test_entry'
  | 'entering'
  | 'not_active'
  | 'open'
  | 'submitted'
  | 'queued'
  | 'closed'
  | 'unknown';

function asObject(resp: unknown): Record<string, unknown> | null {
  return typeof resp === 'object' && resp !== null && !Array.isArray(resp) ? (resp as Record<string, unknown>) : null;
}

/** Ответ сервера → экран. Битое тело, незнакомый status, open/closed/submitted без blocks → unknown. */
export function dayView(resp: unknown): DayView {
  const o = asObject(resp);
  if (!o) return 'unknown';
  const hasBlocks = Array.isArray(o.blocks);
  switch (o.status) {
    case 'not_started':
      return o.test_entry === true ? 'test_entry' : 'not_started';
    case 'entering':
      return 'entering';
    case 'queued':
      return 'queued';
    case 'open':
      if (!hasBlocks) return 'unknown';
      return o.buttons_active === true ? 'open' : 'not_active';
    case 'submitted':
      return hasBlocks ? 'submitted' : 'unknown';
    case 'closed':
      return hasBlocks ? 'closed' : 'unknown';
    default:
      return 'unknown';
  }
}

const WALL_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/;

/** Дата и время «как написано» в строке сервера (пояс участника). Без Date. */
export function wallClock(iso: unknown): { date: string; time: string } | null {
  if (typeof iso !== 'string') return null;
  const m = WALL_RE.exec(iso);
  if (!m) return null;
  return { date: `${m[3]}.${m[2]}`, time: `${m[4]}:${m[5]}` };
}

/** Ключи текстов экрана: 3 служебных + title_key и help_key блоков, без повторов, порядок стабилен. */
export function dayTextKeys(day: DayCurrent | null | undefined): string[] {
  const keys: string[] = Object.values(DAY_TEXT_KEYS);
  const seen = new Set(keys);
  const add = (k: unknown) => {
    if (typeof k === 'string' && k && !seen.has(k)) {
      seen.add(k);
      keys.push(k);
    }
  };
  const blocks = day && Array.isArray(day.blocks) ? day.blocks : [];
  for (const b of blocks) {
    if (!b) continue;
    add(b.title_key);
    add(b.help_key);
  }
  return keys;
}

export const REFETCH_MIN_MS = 1000;
export const REFETCH_MAX_MS = 86_400_000;
export const REFETCH_CLOSED_MS = 60_000;
export const REFETCH_SHORT_MS = 2000;
export const REFETCH_SHORT_TRIES = 5;

function untilMs(target: unknown, nowMs: number): number | null {
  if (typeof target !== 'string') return null;
  const at = Date.parse(target);
  if (Number.isNaN(at)) return null;
  return Math.min(REFETCH_MAX_MS, Math.max(REFETCH_MIN_MS, at - nowMs + 1000));
}

/**
 * Через сколько мс повторить GET (или null — не повторять).
 * queued → queued_until; not_active → active_from; open → deadline_at (+1 с, в [1 с, 24 ч]);
 * closed → 60 с; submitted и entering → 2 с, пока sameViewTries < 5.
 */
export function refetchDelayMs(day: unknown, nowMs: number, sameViewTries: number): number | null {
  const view = dayView(day);
  const o = asObject(day) ?? {};
  switch (view) {
    case 'queued':
      return untilMs(o.queued_until, nowMs);
    case 'not_active':
      return untilMs(o.active_from, nowMs);
    case 'open':
      return untilMs(o.deadline_at, nowMs);
    case 'closed':
      return REFETCH_CLOSED_MS;
    case 'submitted':
    case 'entering':
      return sameViewTries < REFETCH_SHORT_TRIES ? REFETCH_SHORT_MS : null;
    default:
      return null;
  }
}

export const PARTICIPANT_NOT_FOUND_MESSAGE = 'Участник не найден. Закройте и откройте приложение заново.';
export const REOPEN_MESSAGE = 'Закройте и откройте приложение заново.';

/** Сообщение при ошибке GET /day/current. */
export function dayErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 404 && err.code === 'PARTICIPANT_NOT_FOUND') {
    return PARTICIPANT_NOT_FOUND_MESSAGE;
  }
  return errorMessage(err);
}

export type TestEnterAction = 'refetch' | 'retry_1s' | 'reopen' | 'error';

/** Что делать после ошибки POST /day/test-enter. retry_1s экран делает один раз. */
export function testEnterAction(err: unknown): TestEnterAction {
  if (!(err instanceof ApiError)) return 'error';
  if (err.status === 404 && err.code === 'NOT_FOUND') return 'refetch';
  if (err.status === 409 && err.code === 'DAY_STATE_SYNCING') return 'retry_1s';
  if (err.status === 409 && err.code === 'RECONSENT_REQUIRED') return 'reopen';
  return 'error';
}

export const DAY_RETRY_DELAYS_MS = [2000, 4000] as const;

/** Повтор GET /day/current после ошибки: мс или null. Только 503 SERVICE_UNAVAILABLE;
 *  attempt — сколько повторов уже сделано (0 → 2000, 1 → 4000, 2 и больше → null). */
export function dayRetryDelayMs(err: unknown, attempt: number): number | null {
  if (!(err instanceof ApiError)) return null;
  if (err.status !== 503 || err.code !== 'SERVICE_UNAVAILABLE') return null;
  if (!Number.isInteger(attempt) || attempt < 0) return null;
  if (attempt >= DAY_RETRY_DELAYS_MS.length) return null;
  return DAY_RETRY_DELAYS_MS[attempt] ?? null;
}
