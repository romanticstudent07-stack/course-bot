// apps/miniapp/src/components/pause.ts — чистая логика экрана паузы /paused и допуска к дню
// (miniapp-pause-1 §7–§8; Р-6а, Р-20).
//
// Без React и без DOM (тесты — vitest, environment node). Экран — pages/PausedPage/PausedPage.tsx.
// Все решения «можно ли» принимает сервер: клиент не считает допуск к дню по часам,
// время используется только для подписи ETA и для момента очередного GET /pause.
// Тексты — только заглушки (репо публичный). Данные и попытки живут только в памяти:
// не на устройстве, не в адресе, не в логе. Произвольные message/details сервера не показываются.
// Молчание Автора = авто-разрешение: обещания «сгорания» неодобренной заявки нет.
import { ApiError, type PauseInfo, type PauseOverview } from '../api/client.ts';

export const PAUSE_TEXT = {
  title: 'Заглушка: пауза',
  loading: 'Заглушка: загрузка паузы',
  budget: 'Заглушка: дней паузы осталось',
  cycleEnds: 'Заглушка: годовой цикл заканчивается',
  statusNone: 'Заглушка: паузы сейчас нет',
  statusRequested: 'Заглушка: заявка на паузу отправлена',
  statusApproved: 'Заглушка: пауза одобрена и начнётся',
  statusActive: 'Заглушка: вы на паузе',
  statusUnknown: 'Заглушка: состояние паузы не распознано',
  startsAt: 'Заглушка: начало',
  endsAt: 'Заглушка: конец',
  daysLabel: 'Заглушка: дней паузы',
  request: 'Заглушка: запросить паузу',
  requestRetry: 'Заглушка: повторить запрос',
  cancel: 'Заглушка: отменить паузу',
  resume: 'Заглушка: продолжить курс',
  refresh: 'Заглушка: обновить',
  toDay: 'Заглушка: к экрану дня',
  toCard: 'Заглушка: к карточке',
  pending: 'Заглушка: ждём ответа сервера',
  barElapsed: 'Заглушка: полоса 1 — прошло паузы',
  barLeft: 'Заглушка: полоса 2 — осталось паузы',
  barBudget: 'Заглушка: полоса 3 — бюджет пауз',
  etaPrefix: 'Заглушка: до конца паузы',
  etaOver: 'Заглушка: срок паузы истёк, обновите экран',
  noData: 'Заглушка: нет данных',
  dayCheck: 'Заглушка: проверяем паузу',
  dayCheckError: 'Заглушка: не удалось проверить паузу',
  retry: 'Заглушка: повторить',
} as const;

/** Причины отказа (refusal / details.reason) → местные заглушки; неизвестная → нейтральная. */
export const REFUSAL_TEXT = {
  not_approved: 'Заглушка: пауза сейчас недоступна',
  block_lives: 'Заглушка: пауза недоступна без жизней',
  state: 'Заглушка: пауза недоступна в текущем состоянии',
  gap_24h: 'Заглушка: между паузами нужно не меньше 24 ч',
  stage_taken: 'Заглушка: пауза этого Этапа уже использована',
  no_budget: 'Заглушка: дни паузы за год закончились',
  already_open: 'Заглушка: у вас уже есть открытая пауза',
} as const;
export const REFUSAL_UNKNOWN = 'Заглушка: пауза сейчас недоступна по правилам курса';

/** 409 по коду → заглушка. */
export const CONFLICT_TEXT = {
  PAUSE_ALREADY_OPEN: 'Заглушка: пауза уже открыта',
  PAUSE_NOT_CANCELLABLE: 'Заглушка: эту паузу уже нельзя отменить',
  PAUSE_NOT_ACTIVE: 'Заглушка: пауза уже не активна',
} as const;

export const ERROR_TEXT = {
  unauthorized: 'Заглушка: сессия устарела, закройте и откройте приложение',
  notFound: 'Заглушка: участник не найден',
  validation: 'Заглушка: запрос не принят',
  rateLimited: 'Заглушка: слишком много запросов, подождите',
  unavailable: 'Заглушка: сервис временно недоступен',
  conflict: 'Заглушка: состояние паузы изменилось',
  other: 'Заглушка: что-то пошло не так',
  network: 'Заглушка: нет связи, попробуйте ещё раз',
} as const;

export const MAX_PAUSE_DAYS = 7;
export const POLL_LIMIT = 5;
export const POLL_INTERVAL_MS = 2000;
export const ETA_TICK_MS = 30_000;
/** Предел setTimeout (2^31 − 1 мс): дальше таймер ставится на предел и просто вызывает GET. */
export const MAX_TIMER_MS = 2_147_483_647;

export type PauseKind = 'none' | 'requested' | 'approved' | 'active' | 'unknown';

// ---- Разбор ответа GET /pause ----

function isPauseInfo(x: unknown): x is PauseInfo {
  if (typeof x !== 'object' || x === null) return false;
  const p = x as Record<string, unknown>;
  return (
    typeof p.id === 'number' &&
    typeof p.status === 'string' &&
    typeof p.start_at === 'string' &&
    typeof p.planned_end_at === 'string'
  );
}

/** Форма ответа GET /pause по контракту §7; иначе — ошибка (как сеть). */
export function isPauseOverview(x: unknown): x is PauseOverview {
  if (typeof x !== 'object' || x === null) return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o.budget_days_left === 'number' &&
    Number.isFinite(o.budget_days_left) &&
    typeof o.budget_days_total === 'number' &&
    Number.isFinite(o.budget_days_total) &&
    (o.cycle_ends_at === null || typeof o.cycle_ends_at === 'string') &&
    (o.pause === null || isPauseInfo(o.pause)) &&
    typeof o.can_request === 'boolean' &&
    (o.refusal === null || typeof o.refusal === 'string')
  );
}

export function pauseKind(ov: PauseOverview): PauseKind {
  if (ov.pause === null) return 'none';
  const s = ov.pause.status;
  return s === 'requested' || s === 'approved' || s === 'active' ? s : 'unknown';
}

// ---- Допуск к дню (защитная проверка перед /day) ----

export type DayGate = 'day' | 'paused' | 'error';

/** active → /paused; requested / approved / null → день; битый ответ или неизвестный status → ошибка. */
export function dayGate(resp: unknown): DayGate {
  if (!isPauseOverview(resp)) return 'error';
  const kind = pauseKind(resp);
  if (kind === 'active') return 'paused';
  if (kind === 'unknown') return 'error';
  return 'day';
}

/** Один GET /pause → решение; любая ошибка запроса → 'error' (день не монтируется). */
export async function checkDayAccess(get: () => Promise<unknown>): Promise<DayGate> {
  try {
    return dayGate(await get());
  } catch {
    return 'error';
  }
}

/** Монтировать ли экран дня: только после завершённого GET с разрешением. */
export function canMountDay(gate: DayGate | 'loading'): boolean {
  return gate === 'day';
}

// ---- Бюджет, дни, причины ----

/** Наибольшее N для запроса: min(7, budget_days_left), целое; < 1 → 0. */
export function maxRequestDays(ov: PauseOverview): number {
  const left = Math.floor(ov.budget_days_left);
  return Math.max(0, Math.min(MAX_PAUSE_DAYS, left));
}

/** Варианты N: 1…maxRequestDays. */
export function dayOptions(ov: PauseOverview): number[] {
  return Array.from({ length: maxRequestDays(ov) }, (_, i) => i + 1);
}

/** Можно ли отправить запрос на N дней по ответу сервера (окончательно решает POST). */
export function canRequestDays(ov: PauseOverview, days: number): boolean {
  return (
    ov.pause === null &&
    ov.can_request &&
    Number.isInteger(days) &&
    days >= 1 &&
    days <= maxRequestDays(ov)
  );
}

export function refusalText(reason: unknown): string {
  if (typeof reason === 'string' && Object.prototype.hasOwnProperty.call(REFUSAL_TEXT, reason)) {
    return REFUSAL_TEXT[reason as keyof typeof REFUSAL_TEXT];
  }
  return REFUSAL_UNKNOWN;
}

/** details.reason ошибки — безопасное чтение; нет или не строка → null. */
export function errorReason(err: unknown): string | null {
  if (!(err instanceof ApiError)) return null;
  const d = err.details;
  if (typeof d !== 'object' || d === null) return null;
  const r = (d as Record<string, unknown>).reason;
  return typeof r === 'string' ? r : null;
}

/** Ошибка вызова паузы → заглушка. Тексты сервера не показываются. */
export function pauseErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return ERROR_TEXT.network;
  if (err.status === 409) {
    if (err.code === 'PAUSE_REFUSED') return refusalText(errorReason(err));
    if (Object.prototype.hasOwnProperty.call(CONFLICT_TEXT, err.code)) {
      return CONFLICT_TEXT[err.code as keyof typeof CONFLICT_TEXT];
    }
    return ERROR_TEXT.conflict;
  }
  if (err.status === 401) return ERROR_TEXT.unauthorized;
  if (err.status === 404) return ERROR_TEXT.notFound;
  if (err.status === 422) return ERROR_TEXT.validation;
  if (err.status === 429) return ERROR_TEXT.rateLimited;
  if (err.status === 503) return ERROR_TEXT.unavailable;
  return ERROR_TEXT.other;
}

export function isConflict(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
}

/** Исход запроса неизвестен (сеть или 503) → повтор только с той же парой {days, op-id}. */
export function isUncertain(err: unknown): boolean {
  return !(err instanceof ApiError) || err.status === 503;
}

// ---- Время: подписи и ETA (только оставшееся время, не час телефона) ----

const ISO_RE = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/;

/** «ГГГГ-ММ-ДД ЧЧ:ММ» из строки сервера как есть; иначе — заглушка. */
export function isoShort(iso: unknown): string {
  if (typeof iso !== 'string') return PAUSE_TEXT.noData;
  const m = ISO_RE.exec(iso);
  return m ? `${m[1]} ${m[2]}` : PAUSE_TEXT.noData;
}

/** Оставшееся время до planned_end_at: «N д H ч M мин»; истекло — заглушка. */
export function etaText(plannedEnd: string, nowMs: number): string {
  const end = Date.parse(plannedEnd);
  if (Number.isNaN(end)) return PAUSE_TEXT.noData;
  const left = end - nowMs;
  if (left <= 0) return PAUSE_TEXT.etaOver;
  const totalMin = Math.ceil(left / 60_000);
  const d = Math.floor(totalMin / 1440);
  const h = Math.floor((totalMin % 1440) / 60);
  const m = totalMin % 60;
  return `${PAUSE_TEXT.etaPrefix}: ${d} д ${h} ч ${m} мин`;
}

/** Доля 0…100 прошедшего времени паузы; битые даты → 0. */
export function elapsedPercent(p: PauseInfo, nowMs: number): number {
  const start = Date.parse(p.start_at);
  const end = Date.parse(p.planned_end_at);
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return 0;
  const v = ((nowMs - start) / (end - start)) * 100;
  return Math.round(Math.min(100, Math.max(0, v)));
}

export function budgetPercent(ov: PauseOverview): number {
  if (ov.budget_days_total <= 0) return 0;
  const v = (ov.budget_days_left / ov.budget_days_total) * 100;
  return Math.round(Math.min(100, Math.max(0, v)));
}

// ---- Состояние экрана и контроллер с подставными вызовами ----

export interface RequestAttempt {
  days: number;
  opId: string;
}

export interface PauseSnapshot {
  load: 'loading' | 'ready' | 'error';
  overview: PauseOverview | null;
  loadError: unknown;
  actionError: unknown;
  /** Идёт действие (запрос / отмена / продолжение и его перечитывание) — кнопки заблокированы. */
  busy: boolean;
  /** Попытка запроса с неопределённым исходом: days не меняются, повтор — с той же парой. */
  attempt: RequestAttempt | null;
  days: number;
  polling: boolean;
  /** До этого момента (мс) нет фоновых GET и повтора действий (429 + Retry-After). */
  rateLimitedUntil: number | null;
  now: number;
}

export interface PauseDeps {
  getPause: () => Promise<unknown>;
  postPauseRequest: (days: number, clientOpId: string) => Promise<unknown>;
  postPauseCancel: () => Promise<unknown>;
  postPauseResume: () => Promise<unknown>;
  newOpId: () => string;
  now: () => number;
  setTimer: (fn: () => void, ms: number) => unknown;
  clearTimer: (handle: unknown) => void;
}

export interface PauseController {
  start: () => void;
  refresh: () => void;
  setDays: (days: number) => void;
  request: () => Promise<void>;
  cancel: () => Promise<void>;
  resume: () => Promise<void>;
  dispose: () => void;
  snapshot: () => PauseSnapshot;
}

type Slot = 'startAt' | 'eta' | 'tick' | 'poll' | 'rate';
const STALE = Symbol('stale');

function samePause(ov: PauseOverview, prev: PauseInfo): boolean {
  return ov.pause !== null && ov.pause.id === prev.id && ov.pause.status === prev.status;
}

export function initialSnapshot(nowMs: number): PauseSnapshot {
  return {
    load: 'loading',
    overview: null,
    loadError: null,
    actionError: null,
    busy: false,
    attempt: null,
    days: 1,
    polling: false,
    rateLimitedUntil: null,
    now: nowMs,
  };
}

export function isRateLimited(s: PauseSnapshot, nowMs: number): boolean {
  return s.rateLimitedUntil !== null && nowMs < s.rateLimitedUntil;
}

/**
 * Контроллер экрана /paused. Ответы старых запросов и ответы после dispose игнорируются;
 * таймеры очищаются. POST после ошибки сам не повторяется.
 */
export function createPauseController(
  deps: PauseDeps,
  onChange: (s: PauseSnapshot) => void,
): PauseController {
  let s = initialSnapshot(deps.now());
  let disposed = false;
  let readSeq = 0;
  const slots: Partial<Record<Slot, unknown>> = {};

  const emit = (patch: Partial<PauseSnapshot>) => {
    if (disposed) return;
    s = { ...s, ...patch, now: deps.now() };
    onChange(s);
  };

  const clearSlot = (slot: Slot) => {
    if (slots[slot] !== undefined) {
      deps.clearTimer(slots[slot]);
      delete slots[slot];
    }
  };

  const setSlot = (slot: Slot, fn: () => void, ms: number) => {
    clearSlot(slot);
    slots[slot] = deps.setTimer(() => {
      delete slots[slot];
      if (!disposed) fn();
    }, Math.min(MAX_TIMER_MS, Math.max(0, ms)));
  };

  const limited = () => isRateLimited(s, deps.now());

  const noteError = (err: unknown) => {
    if (err instanceof ApiError && err.status === 429 && err.retryAfter !== null) {
      const until = deps.now() + err.retryAfter * 1000;
      emit({ rateLimitedUntil: until });
      setSlot('rate', () => emit({ rateLimitedUntil: null }), until - deps.now());
    }
  };

  const scheduleStatusTimers = (ov: PauseOverview) => {
    clearSlot('startAt');
    clearSlot('eta');
    clearSlot('tick');
    const kind = pauseKind(ov);
    if ((kind === 'requested' || kind === 'approved') && ov.pause !== null) {
      const prev = ov.pause;
      const ms = Date.parse(prev.start_at) - deps.now();
      // Только будущий start_at: иначе — ручное «Обновить» (без цикла GET).
      if (ms > 0) setSlot('startAt', () => poll((o) => samePause(o, prev)), ms);
    }
    if (kind === 'active' && ov.pause !== null) {
      const ms = Date.parse(ov.pause.planned_end_at) - deps.now();
      // Истечение ETA только вызывает GET: статус не меняет и день не открывает.
      if (ms > 0) setSlot('eta', () => { if (!limited()) void read(); }, ms);
      const tick = () => {
        emit({});
        setSlot('tick', tick, ETA_TICK_MS);
      };
      setSlot('tick', tick, ETA_TICK_MS);
    }
  };

  const apply = (ov: PauseOverview) => {
    const attempt = ov.pause !== null ? null : s.attempt;
    const max = maxRequestDays(ov);
    const days = attempt !== null ? attempt.days : Math.min(Math.max(1, s.days), Math.max(1, max));
    emit({ load: 'ready', overview: ov, loadError: null, attempt, days });
    scheduleStatusTimers(ov);
  };

  /** Один GET /pause; устаревший ответ → STALE; ошибка → null. */
  const read = async (): Promise<PauseOverview | null | typeof STALE> => {
    const id = ++readSeq;
    try {
      const resp = await deps.getPause();
      if (disposed || id !== readSeq) return STALE;
      if (!isPauseOverview(resp)) throw new Error('bad pause response');
      apply(resp);
      return resp;
    } catch (err: unknown) {
      if (disposed || id !== readSeq) return STALE;
      noteError(err);
      clearSlot('startAt');
      clearSlot('eta');
      clearSlot('tick');
      emit({ load: 'error', loadError: err });
      return null;
    }
  };

  const stopPoll = () => {
    clearSlot('poll');
    if (s.polling) emit({ polling: false });
  };

  /** GET сразу и до POLL_LIMIT повторов через POLL_INTERVAL_MS, пока isSame; затем — вручную. */
  const poll = (isSame: (ov: PauseOverview) => boolean, onDone?: () => void) => {
    clearSlot('poll');
    let retries = 0;
    emit({ polling: true });
    const finish = () => {
      emit({ polling: false });
      onDone?.();
    };
    const step = async () => {
      if (limited()) {
        finish();
        return;
      }
      const ov = await read();
      if (ov === STALE) {
        onDone?.();
        return;
      }
      if (ov === null || !isSame(ov) || retries >= POLL_LIMIT) {
        finish();
        return;
      }
      retries += 1;
      setSlot('poll', () => void step(), POLL_INTERVAL_MS);
    };
    void step();
  };

  const act = async (kind: 'cancel' | 'resume') => {
    const ov = s.overview;
    if (disposed || s.busy || limited() || s.load !== 'ready' || ov === null || ov.pause === null) return;
    const k = pauseKind(ov);
    if (kind === 'cancel' && k !== 'requested' && k !== 'approved') return;
    if (kind === 'resume' && k !== 'active') return;
    const prev = ov.pause;
    emit({ busy: true, actionError: null });
    try {
      await (kind === 'cancel' ? deps.postPauseCancel() : deps.postPauseResume());
      if (disposed) return;
      // 202 — событие принято, не новый статус: перечитываем до смены той же паузы.
      poll((o) => samePause(o, prev), () => emit({ busy: false }));
    } catch (err: unknown) {
      if (disposed) return;
      noteError(err);
      emit({ actionError: err });
      if (isConflict(err)) await read();
      emit({ busy: false });
    }
  };

  return {
    start: () => {
      void read();
    },
    refresh: () => {
      if (disposed || s.busy || limited()) return;
      stopPoll();
      emit({ load: s.overview === null ? 'loading' : s.load });
      void read();
    },
    setDays: (days: number) => {
      if (disposed || s.busy || s.attempt !== null || s.overview === null) return;
      if (!Number.isInteger(days) || days < 1 || days > maxRequestDays(s.overview)) return;
      emit({ days });
    },
    request: async () => {
      const ov = s.overview;
      if (disposed || s.busy || limited() || s.load !== 'ready' || ov === null) return;
      if (s.attempt === null && !canRequestDays(ov, s.days)) return;
      const attempt = s.attempt ?? { days: s.days, opId: deps.newOpId() };
      emit({ busy: true, attempt, actionError: null });
      try {
        await deps.postPauseRequest(attempt.days, attempt.opId);
        if (disposed) return;
        // 201 — заявка создана; статус берём только из GET.
        emit({ attempt: null });
        await read();
        emit({ busy: false });
      } catch (err: unknown) {
        if (disposed) return;
        noteError(err);
        if (isUncertain(err)) {
          emit({ busy: false, actionError: err });
          return;
        }
        emit({ attempt: null, actionError: err });
        if (isConflict(err)) await read();
        emit({ busy: false });
      }
    },
    cancel: () => act('cancel'),
    resume: () => act('resume'),
    dispose: () => {
      disposed = true;
      readSeq += 1;
      for (const slot of Object.keys(slots) as Slot[]) clearSlot(slot);
    },
    snapshot: () => s,
  };
}

// ---- Модель вида (что показать и какие кнопки доступны) ----

export interface PauseViewModel {
  kind: PauseKind;
  statusText: string;
  budgetText: string;
  cycleText: string | null;
  bounds: { start: string; end: string } | null;
  eta: string | null;
  bars: { label: string; value: number }[];
  refusal: string | null;
  errorText: string | null;
  dayOptions: number[];
  days: number;
  showRequest: boolean;
  requestEnabled: boolean;
  requestLabel: string;
  daysLocked: boolean;
  showCancel: boolean;
  showResume: boolean;
  actionsEnabled: boolean;
  refreshEnabled: boolean;
  showToDay: boolean;
}

const STATUS_TEXT: Record<PauseKind, string> = {
  none: PAUSE_TEXT.statusNone,
  requested: PAUSE_TEXT.statusRequested,
  approved: PAUSE_TEXT.statusApproved,
  active: PAUSE_TEXT.statusActive,
  unknown: PAUSE_TEXT.statusUnknown,
};

/** Модель готового экрана (load === 'ready', overview есть). */
export function pauseViewModel(s: PauseSnapshot, ov: PauseOverview): PauseViewModel {
  const kind = pauseKind(ov);
  const limited = isRateLimited(s, s.now);
  const free = !s.busy && !limited;
  const p = ov.pause;
  const bars =
    kind === 'active' && p !== null
      ? [
          { label: PAUSE_TEXT.barElapsed, value: elapsedPercent(p, s.now) },
          { label: PAUSE_TEXT.barLeft, value: 100 - elapsedPercent(p, s.now) },
          { label: PAUSE_TEXT.barBudget, value: budgetPercent(ov) },
        ]
      : [];
  const showRequest = kind === 'none';
  const requestEnabled =
    showRequest && free && (s.attempt !== null || canRequestDays(ov, s.days));
  return {
    kind,
    statusText: STATUS_TEXT[kind],
    budgetText: `${PAUSE_TEXT.budget}: ${ov.budget_days_left} / ${ov.budget_days_total}`,
    cycleText: ov.cycle_ends_at === null ? null : `${PAUSE_TEXT.cycleEnds}: ${isoShort(ov.cycle_ends_at)}`,
    bounds:
      p !== null && kind !== 'unknown'
        ? { start: isoShort(p.start_at), end: isoShort(p.planned_end_at) }
        : null,
    eta: kind === 'active' && p !== null ? etaText(p.planned_end_at, s.now) : null,
    bars,
    // Без открытой паузы и без разрешения — причина; already_open рядом с паузой не нужна.
    refusal: kind === 'none' && !ov.can_request ? refusalText(ov.refusal) : null,
    errorText: s.actionError === null ? null : pauseErrorMessage(s.actionError),
    dayOptions: dayOptions(ov),
    days: s.days,
    showRequest,
    requestEnabled,
    requestLabel: s.attempt !== null ? PAUSE_TEXT.requestRetry : PAUSE_TEXT.request,
    daysLocked: s.attempt !== null || s.busy,
    showCancel: kind === 'requested' || kind === 'approved',
    showResume: kind === 'active',
    actionsEnabled: free,
    refreshEnabled: free,
    showToDay: kind !== 'active',
  };
}
