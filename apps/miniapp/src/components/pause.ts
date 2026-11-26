// apps/miniapp/src/components/pause.ts — координатор чтений и операций паузы (miniapp-pause-c1, T5-C1).
// Без React и без хранилищ: состояние живёт в замыкании, наружу — только onView(снимок).
// Регрессии #267 (t5-bc §4, miniapp-pause-canon:70–71):
//   2 — серия старта: start_at <= now и пауза ещё не active → одна серия на (pause.id, start_at)
//       за жизнь координатора: 1 GET сразу + до 5 повторов через 2 с; повторный apply того же
//       ключа серию не перезапускает; серия кончается раньше, если GET показал другое состояние;
//   3 — readSeq: один координатор чтений; применяется только ответ последнего reread, прошлый
//       запрос получает abort; финал серии сбрасывает только свой флаг polling.
// Таймер — только deps.schedule (серия старта). Повторов GET после ошибки нет (это не POST-backoff).
// Три POST здесь не вызываются: операции ставятся в очередь (pauseQueue.ts), отправляет pauseSend.ts.
// Бизнес-409 — сообщение и reread, без очистки (R-2026-11-21); коллизия — текст R339 и отправка закрыта.
// В main модуль никто не вызывает (экран /paused и запуск — c3).

import { ApiError, type PauseStatus } from '../api/client.ts';
import { PAUSE_CONFLICT_TEXT, type PauseQueue, type PauseQueueOutcome } from './pauseQueue.ts';
import type { PauseOpArgs, PauseOpKind } from './pauseQueueStore.ts';

export { PAUSE_CONFLICT_TEXT };

// Тексты — технические заглушки [ШТАБ-тех].
export const PAUSE_REOPEN_TEXT = 'Не удалось поставить операцию. Переоткройте Mini App.';
export const PAUSE_START_DATE_PASSED_TEXT = 'Дата начала паузы уже прошла. Подтвердите паузу заново.';
export const PAUSE_STOPPED_TEXT = 'Операцию не удалось выполнить. Обновите экран и попробуйте снова.';
export const PAUSE_BUSINESS_TEXTS: Readonly<Record<string, string>> = {
  PAUSE_ALREADY_OPEN: 'Пауза уже запрошена или идёт.',
  PAUSE_REFUSED: 'Паузу сейчас взять нельзя.',
  PAUSE_NOT_CANCELLABLE: 'Заявку уже нельзя отменить.',
  PAUSE_NOT_ACTIVE: 'Активной паузы нет.',
};
export const PAUSE_BUSINESS_FALLBACK_TEXT = 'Операция отклонена. Обновите экран.';

/** Серия старта: 1 GET сразу + PAUSE_START_SERIES_REPEATS повторов через PAUSE_START_SERIES_STEP_MS. */
export const PAUSE_START_SERIES_REPEATS = 5;
export const PAUSE_START_SERIES_STEP_MS = 2_000;
/** Статус активной паузы (apps/api/app/routers/pause.py:113, ACTIVE = "active"). */
export const PAUSE_STATUS_ACTIVE = 'active';
/** Статусы заявки, которую можно отменить (apps/api/app/routers/pause.py:112, CANCELLABLE). */
export const PAUSE_STATUS_CANCELLABLE = ['requested', 'approved'] as const;

export interface PauseViewError {
  /** HTTP-статус; 0 — сеть или таймаут. */
  status: number;
  code: string;
  retryAfter: number | null;
}

export interface PauseView {
  /** Последний применённый GET /pause или null. */
  data: PauseStatus | null;
  /** Идёт последний reread. */
  loading: boolean;
  error: PauseViewError | null;
  message: string | null;
  /** Операция поставлена и ждёт исхода. */
  busy: boolean;
  /** Идёт серия старта. */
  polling: boolean;
  /** start_date_passed: нужно новое подтверждение участника. */
  confirmStart: boolean;
  /** Коллизия op-id: операции закрыты до перезапуска. */
  closed: boolean;
}

export interface PauseCoordinatorDeps {
  getPause(signal?: AbortSignal): Promise<PauseStatus>;
  queue: Pick<PauseQueue, 'enqueue' | 'tick' | 'resumeAuth'>;
  onView(view: PauseView): void;
  now(): number;
  /** Отложенный вызов той же формы, что PauseQueueDeps.schedule; возвращает отмену. */
  schedule(fn: () => void, ms: number): () => void;
}

export interface PauseCoordinator {
  reread(): Promise<void>;
  request(days: number): Promise<boolean>;
  cancel(pauseId: number): Promise<boolean>;
  resume(pauseId: number): Promise<boolean>;
  onOutcome(event: PauseQueueOutcome): void;
  dispose(): void;
}

interface Series {
  key: string;
  count: number;
  cancel: (() => void) | null;
}

function isAbort(err: unknown): boolean {
  return typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError';
}

function toViewError(err: unknown): PauseViewError {
  if (err instanceof ApiError) return { status: err.status, code: err.code, retryAfter: err.retryAfter };
  return { status: 0, code: 'NETWORK_ERROR', retryAfter: null };
}

export function createPauseCoordinator(deps: PauseCoordinatorDeps): PauseCoordinator {
  let readSeq = 0;
  let ctrl: AbortController | null = null;
  let disposed = false;

  let data: PauseStatus | null = null;
  let loading = false;
  let error: PauseViewError | null = null;
  let message: string | null = null;
  let busy = false;
  let confirmStart = false;
  let closed = false;

  let series: Series | null = null;
  const startedKeys = new Set<string>();

  function emit(): void {
    if (disposed) return;
    deps.onView({ data, loading, error, message, busy, polling: series !== null, confirmStart, closed });
  }

  function finishSeries(s: Series): void {
    if (series !== s) return; // чужой финал не трогает текущую серию
    if (s.cancel !== null) s.cancel();
    s.cancel = null;
    series = null;
    emit();
  }

  function seriesStep(s: Series): void {
    if (disposed || series !== s) return;
    s.cancel = null;
    s.count += 1;
    void reread().then(() => {
      if (disposed || series !== s) return;
      if (s.count >= 1 + PAUSE_START_SERIES_REPEATS) {
        finishSeries(s);
        return;
      }
      s.cancel = deps.schedule(() => seriesStep(s), PAUSE_START_SERIES_STEP_MS);
    });
  }

  function afterApply(status: PauseStatus): void {
    const p = status.pause;
    const key = p ? `${p.id}|${p.start_at}` : null;
    if (series !== null && (p === null || p.status === PAUSE_STATUS_ACTIVE || key !== series.key)) finishSeries(series);
    if (p === null || key === null || p.status === PAUSE_STATUS_ACTIVE) return;
    const startAt = Date.parse(p.start_at);
    if (!Number.isFinite(startAt) || startAt > deps.now()) return;
    if (startedKeys.has(key)) return; // один старт серии на (pause.id, start_at)
    startedKeys.add(key);
    const s: Series = { key, count: 0, cancel: null };
    series = s;
    emit();
    seriesStep(s);
  }

  async function reread(): Promise<void> {
    if (disposed) return;
    readSeq += 1;
    const my = readSeq;
    if (ctrl !== null) ctrl.abort();
    const c = new AbortController();
    ctrl = c;
    loading = true;
    emit();
    let result: PauseStatus;
    try {
      result = await deps.getPause(c.signal);
    } catch (err) {
      if (disposed || my !== readSeq) return;
      ctrl = null;
      loading = false;
      if (isAbort(err)) {
        emit();
        return;
      }
      error = toViewError(err);
      emit();
      return;
    }
    if (disposed || my !== readSeq) return;
    ctrl = null;
    loading = false;
    data = result;
    error = null;
    emit();
    deps.queue.resumeAuth();
    afterApply(result);
  }

  async function startOp(kind: PauseOpKind, args: PauseOpArgs | null): Promise<boolean> {
    if (disposed || closed || busy || args === null) return false;
    busy = true;
    confirmStart = false;
    message = null;
    emit();
    try {
      await deps.queue.enqueue(kind, args);
    } catch {
      busy = false;
      message = PAUSE_REOPEN_TEXT;
      emit();
      return false;
    }
    await deps.queue.tick();
    return true;
  }

  function request(days: number): Promise<boolean> {
    const d = data;
    return startOp('request', d !== null && d.can_request ? { days, start_date: d.start_date } : null);
  }

  function cancel(pauseId: number): Promise<boolean> {
    return startOp('cancel', { pause_id: pauseId });
  }

  function resume(pauseId: number): Promise<boolean> {
    return startOp('resume', { pause_id: pauseId });
  }

  function onOutcome(event: PauseQueueOutcome): void {
    if (disposed) return;
    switch (event.type) {
      case 'done':
        busy = false;
        message = null;
        emit();
        void reread();
        return;
      case 'business':
        busy = false;
        if (event.code === 'PAUSE_REFUSED' && event.details?.reason === 'start_date_passed') {
          message = PAUSE_START_DATE_PASSED_TEXT;
          confirmStart = true;
        } else {
          message = PAUSE_BUSINESS_TEXTS[event.code] ?? PAUSE_BUSINESS_FALLBACK_TEXT;
        }
        emit();
        void reread();
        return;
      case 'stopped':
        busy = false;
        message = PAUSE_STOPPED_TEXT;
        emit();
        void reread();
        return;
      case 'conflict':
        busy = false;
        closed = true;
        message = event.text;
        emit();
        return;
      case 'wiped':
        busy = false;
        emit();
        return;
    }
  }

  function dispose(): void {
    if (disposed) return;
    if (series !== null && series.cancel !== null) series.cancel();
    series = null;
    if (ctrl !== null) ctrl.abort();
    ctrl = null;
    disposed = true;
  }

  return { reread, request, cancel, resume, onOutcome, dispose };
}
