// apps/miniapp/src/components/pausedScreen.ts — вид экрана /paused (miniapp-pause-c3b §7.4), без React.
// Чистые функции: «сейчас» приходит аргументом nowMs, часов и таймеров здесь нет.
// Полосы — решение Автора 26.11 (§15, вариант А): «Дни паузы в цикле» (budget_days_left / budget_days_total)
// и «Ход паузы» (только active, от start_at до planned_end_at, обрезка 0..100), плюс ETA.
// Вход — снимок координатора pause.ts (PauseView из onView). Кнопки решает статус паузы:
// это экран управления паузой, а не кнопки дня. ETA без пояса (решение ШТАБа З2, К-5).
// pauseErrorToApi (c3b-2): ошибка снимка → ApiError или TypeError для retryAtFrom и dayErrorMessage.
// Тексты — заглушки интерфейса [ШТАБ-тех], не тексты курса.
import { ApiError, type PauseStatus } from '../api/client.ts';
import {
  PAUSE_CONFLICT_TEXT,
  PAUSE_STATUS_ACTIVE,
  PAUSE_STATUS_CANCELLABLE,
  type PauseView,
  type PauseViewError,
} from './pause.ts';

export const PAUSED_TEXT = {
  etaPrefix: 'До конца паузы',
  etaEnding: 'Пауза завершается',
  budgetBar: 'Дни паузы в цикле',
  progressBar: 'Ход паузы',
} as const;

/** Известные коды refusal из GET /pause (client.ts: "already_open"); прочие — общий текст. */
export const REFUSAL_TEXTS: Readonly<Record<string, string>> = {
  already_open: 'Пауза уже запрошена или идёт.',
};
export const REFUSAL_FALLBACK_TEXT = 'Паузу сейчас взять нельзя.';

export type PausedButton = 'request' | 'cancel' | 'resume';

export type PausedKind =
  | 'loading'
  | 'error'
  | 'closed'
  | 'request'
  | 'refused'
  | 'cancellable'
  | 'active'
  | 'other';

export interface PauseBar {
  id: 'budget' | 'progress';
  label: string;
  /** Целое 0..100. */
  percent: number;
}

export interface PausedViewModel {
  kind: PausedKind;
  buttons: PausedButton[];
  bars: PauseBar[];
  eta: string | null;
  message: string | null;
}

const HOUR_MS = 3_600_000;

/** «До конца паузы: N дн. M ч» (часы вверх); срок прошёл — «Пауза завершается»; битая дата — null. */
export function formatEta(plannedEndAt: string, nowMs: number): string | null {
  const end = Date.parse(plannedEndAt);
  if (!Number.isFinite(end)) return null;
  const left = end - nowMs;
  if (left <= 0) return PAUSED_TEXT.etaEnding;
  const hours = Math.ceil(left / HOUR_MS);
  return `${PAUSED_TEXT.etaPrefix}: ${Math.floor(hours / 24)} дн. ${hours % 24} ч`;
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}

/** Полосы варианта А. total 0 → полосы бюджета нет; «Ход паузы» — только при active. */
export function pauseBars(status: PauseStatus, nowMs: number): PauseBar[] {
  const bars: PauseBar[] = [];
  if (status.budget_days_total > 0) {
    bars.push({
      id: 'budget',
      label: PAUSED_TEXT.budgetBar,
      percent: clampPercent((status.budget_days_left / status.budget_days_total) * 100),
    });
  }
  const p = status.pause;
  if (p !== null && p.status === PAUSE_STATUS_ACTIVE) {
    const start = Date.parse(p.start_at);
    const end = Date.parse(p.planned_end_at);
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
      bars.push({
        id: 'progress',
        label: PAUSED_TEXT.progressBar,
        percent: clampPercent(((nowMs - start) / (end - start)) * 100),
      });
    }
  }
  return bars;
}

/** Код отказа → короткий текст; неизвестный или null → общий текст. */
export function refusalText(code: string | null): string {
  if (code === null) return REFUSAL_FALLBACK_TEXT;
  return REFUSAL_TEXTS[code] ?? REFUSAL_FALLBACK_TEXT;
}

/**
 * Ошибка GET из снимка координатора → значение для retryAtFrom и dayErrorMessage.
 * status > 0 → ApiError(status, code, '', retryAfter); status 0 (сеть или таймаут) → TypeError(code).
 */
export function pauseErrorToApi(e: PauseViewError): unknown {
  if (e.status > 0) return new ApiError(e.status, e.code, '', e.retryAfter);
  return new TypeError(e.code);
}

function isCancellable(status: string): boolean {
  return (PAUSE_STATUS_CANCELLABLE as readonly string[]).includes(status);
}

/**
 * Снимок координатора → вид экрана.
 * closed → текст коллизии, без кнопок; данных нет → loading или error;
 * pause null и can_request → request; pause null и !can_request → refused с текстом отказа;
 * status из PAUSE_STATUS_CANCELLABLE → cancel; status = PAUSE_STATUS_ACTIVE → resume, полосы и ETA;
 * другой status → без кнопок.
 */
export function pausedView(snapshot: PauseView, nowMs: number): PausedViewModel {
  if (snapshot.closed) {
    return { kind: 'closed', buttons: [], bars: [], eta: null, message: snapshot.message ?? PAUSE_CONFLICT_TEXT };
  }
  const data = snapshot.data;
  if (data === null) {
    return {
      kind: snapshot.error !== null ? 'error' : 'loading',
      buttons: [],
      bars: [],
      eta: null,
      message: snapshot.message,
    };
  }
  const bars = pauseBars(data, nowMs);
  const p = data.pause;
  if (p === null) {
    if (data.can_request) {
      return { kind: 'request', buttons: ['request'], bars, eta: null, message: snapshot.message };
    }
    return { kind: 'refused', buttons: [], bars, eta: null, message: snapshot.message ?? refusalText(data.refusal) };
  }
  if (isCancellable(p.status)) {
    return { kind: 'cancellable', buttons: ['cancel'], bars, eta: null, message: snapshot.message };
  }
  if (p.status === PAUSE_STATUS_ACTIVE) {
    return {
      kind: 'active',
      buttons: ['resume'],
      bars,
      eta: formatEta(p.planned_end_at, nowMs),
      message: snapshot.message,
    };
  }
  return { kind: 'other', buttons: [], bars, eta: null, message: snapshot.message };
}
