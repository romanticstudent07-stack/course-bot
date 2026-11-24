// apps/miniapp/src/components/pauseQueue.ts — воркер очереди пауз (miniapp-pause-b2, T5-B2).
// Одна операция на владельца: слот из pauseQueueStore.ts (B1), фазы queued / uncertain / stopped.
// Повтор — тем же opId и теми же args (И4 R339 write_queue, И2 idempotency_keys);
// backoff min(60 с, 2 с × 2^attempt); 429 → notBefore по Retry-After, сохраняется в слоте.
// 409 IDEMPOTENCY_CONFLICT → флаг полной очистки, отправка закрыта, текст R339 (R-2026-11-21);
//   клиент коллизию не логирует, аудит — только сервер.
// Смена владельца → wipeAll сразу (И4 R380 on_tg_user_id_change).
// Межвкладочный lock — navigator.locks 'course-bot-pause-queue' с ifAvailable; без него повтор
//   безопасен: тот же opId, сервер вернёт прежний ответ.
// Отправитель передаётся снаружи (deps.send). В main модуль никто не вызывает (запуск — C2).

import { ApiError } from '../api/client.ts';
import type { PauseOpArgs, PauseOpKind, PauseQueueStore, PauseSlot } from './pauseQueueStore.ts';

export const PAUSE_LOCK_NAME = 'course-bot-pause-queue';
export const PAUSE_BACKOFF_BASE_MS = 2_000;
export const PAUSE_BACKOFF_MAX_MS = 60_000;
/** И4 R339 conflict_ux.on_server_409.show_error — дословно. */
export const PAUSE_CONFLICT_TEXT = 'локальные данные повреждены; переоткройте Mini App';

const BUSINESS_409 = new Set(['PAUSE_ALREADY_OPEN', 'PAUSE_REFUSED', 'PAUSE_NOT_CANCELLABLE', 'PAUSE_NOT_ACTIVE']);

export type PauseQueueOutcome =
  | { type: 'done'; kind: PauseOpKind; result: unknown }
  | { type: 'conflict'; text: string }
  | { type: 'business'; code: string; details?: unknown }
  | { type: 'stopped'; status: number; code: string }
  | { type: 'wiped' };

/** Подмножество Web Locks API, которое нужно воркеру. */
export interface PauseLockManager {
  request<T>(name: string, options: { ifAvailable: true }, callback: (lock: unknown) => Promise<T>): Promise<T>;
}

export interface PauseQueueDeps {
  store: PauseQueueStore;
  /** Отправка слота на сервер; успех (201/202) — resolve, ошибка — ApiError или сеть / таймаут. */
  send(slot: PauseSlot): Promise<unknown>;
  getOwnerId(): string | null;
  now(): number;
  /** UUID v4; C1 передаёт newClientOpId из client.ts. */
  newOpId(): string;
  /** Отложенный вызов; возвращает отмену. */
  schedule(fn: () => void, ms: number): () => void;
  /** undefined → navigator.locks, если есть; null → без межвкладочного lock. */
  locks?: PauseLockManager | null;
  onOutcome(event: PauseQueueOutcome): void;
}

export interface PauseQueue {
  enqueue(kind: PauseOpKind, args: PauseOpArgs): Promise<string>;
  tick(): Promise<void>;
  resumeAuth(): void;
  stop(): void;
}

/** Задержка перед повтором после неудачной попытки номер attempt (с 0): 2, 4, 8 … 60 с. */
export function pauseBackoffMs(attempt: number): number {
  const exp = Math.min(Math.max(0, Math.floor(attempt)), 30);
  return Math.min(PAUSE_BACKOFF_MAX_MS, PAUSE_BACKOFF_BASE_MS * 2 ** exp);
}

function defaultLocks(): PauseLockManager | null {
  const nav = (globalThis as { navigator?: { locks?: unknown } }).navigator;
  const locks = nav?.locks;
  return locks && typeof (locks as PauseLockManager).request === 'function' ? (locks as PauseLockManager) : null;
}

export function createPauseQueue(deps: PauseQueueDeps): PauseQueue {
  const { store } = deps;
  const locks = deps.locks === undefined ? defaultLocks() : deps.locks;

  let halted = false; // stop()
  let closed = false; // коллизия: отправка закрыта до перезагрузки
  let authOwner: string | null = null; // 401/403: ждём resumeAuth этого владельца
  let cancelTimer: (() => void) | null = null;
  let inflight: Promise<void> | null = null;

  function clearTimer(): void {
    if (cancelTimer !== null) {
      cancelTimer();
      cancelTimer = null;
    }
  }

  function setTimer(ms: number): void {
    if (halted || closed) return;
    clearTimer();
    cancelTimer = deps.schedule(() => {
      cancelTimer = null;
      void tick();
    }, Math.max(0, ms));
  }

  async function withLock(fn: () => Promise<void>): Promise<void> {
    if (locks === null) {
      await fn();
      return;
    }
    await locks.request(PAUSE_LOCK_NAME, { ifAvailable: true }, async (lock) => {
      if (lock === null) return; // другая вкладка уже отправляет
      await fn();
    });
  }

  async function retryLater(slot: PauseSlot, retryAfterSec: number | null): Promise<void> {
    const delay =
      retryAfterSec !== null && Number.isFinite(retryAfterSec) && retryAfterSec > 0
        ? retryAfterSec * 1000
        : pauseBackoffMs(slot.attempt);
    await store.write({ ...slot, phase: 'uncertain', attempt: slot.attempt + 1, notBefore: deps.now() + delay });
    setTimer(delay);
  }

  async function handleError(slot: PauseSlot, err: unknown): Promise<void> {
    if (!(err instanceof ApiError) || typeof err.status !== 'number') {
      await retryLater(slot, null); // сеть, таймаут
      return;
    }
    const { status, code } = err;
    if (status === 409 && code === 'IDEMPOTENCY_CONFLICT') {
      await store.setWipePending();
      closed = true;
      clearTimer();
      deps.onOutcome({ type: 'conflict', text: PAUSE_CONFLICT_TEXT });
      return;
    }
    if (status === 409 && BUSINESS_409.has(code)) {
      await store.clear(slot.ownerId);
      deps.onOutcome({ type: 'business', code });
      return;
    }
    if (status === 429) {
      await retryLater(slot, err.retryAfter);
      return;
    }
    if (status === 401 || status === 403) {
      authOwner = slot.ownerId;
      return;
    }
    if (status >= 500) {
      await retryLater(slot, null);
      return;
    }
    // 404, 422, прочие 409 и остальные 4xx — без автоповтора.
    await store.write({ ...slot, phase: 'stopped' });
    deps.onOutcome({ type: 'stopped', status, code });
  }

  async function sendUnderLock(owner: string, opId: string): Promise<void> {
    const cur = await store.read(owner, deps.now());
    if (cur === null || cur.opId !== opId || cur.phase === 'stopped') return;
    const t = deps.now();
    if (t < cur.notBefore) {
      setTimer(cur.notBefore - t);
      return;
    }
    const sending: PauseSlot = { ...cur, phase: 'uncertain' };
    await store.write(sending);
    let result: unknown;
    try {
      result = await deps.send(sending);
    } catch (err) {
      await handleError(sending, err);
      return;
    }
    await store.clear(owner);
    deps.onOutcome({ type: 'done', kind: sending.kind, result });
  }

  async function runTick(): Promise<void> {
    if (halted || closed) return;
    if (await store.isWipePending()) {
      clearTimer();
      await store.wipeAll();
      authOwner = null;
      deps.onOutcome({ type: 'wiped' });
      return;
    }
    if (store.sendClosed()) return;
    const owner = deps.getOwnerId();
    if (owner === null) return;
    const slot = await store.read(owner, deps.now());
    if (slot === null) return;
    if (slot.ownerId !== owner) {
      clearTimer();
      authOwner = null;
      await store.wipeAll();
      return;
    }
    if (slot.phase === 'stopped') return;
    if (authOwner !== null) return; // ждём resumeAuth
    const now = deps.now();
    if (now < slot.notBefore) {
      setTimer(slot.notBefore - now);
      return;
    }
    await withLock(() => sendUnderLock(owner, slot.opId));
  }

  function tick(): Promise<void> {
    if (inflight !== null) return inflight;
    inflight = runTick().finally(() => {
      inflight = null;
    });
    return inflight;
  }

  async function enqueue(kind: PauseOpKind, args: PauseOpArgs): Promise<string> {
    const owner = deps.getOwnerId();
    if (owner === null) throw new Error('pauseQueue: no owner');
    const existing = await store.read(owner, deps.now());
    if (existing !== null && existing.phase !== 'stopped') return existing.opId;
    if (existing !== null) await store.clear(owner);
    const now = deps.now();
    const slot: PauseSlot = {
      ownerId: owner,
      kind,
      args,
      opId: deps.newOpId(),
      phase: 'queued',
      attempt: 0,
      notBefore: now,
      savedAt: now,
    };
    await store.write(slot);
    return slot.opId;
  }

  function resumeAuth(): void {
    if (authOwner === null || deps.getOwnerId() !== authOwner) return;
    authOwner = null;
    void tick();
  }

  function stop(): void {
    halted = true;
    clearTimer();
  }

  return { enqueue, tick, resumeAuth, stop };
}
