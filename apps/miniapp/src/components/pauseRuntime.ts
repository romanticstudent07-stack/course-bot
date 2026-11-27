// apps/miniapp/src/components/pauseRuntime.ts — запуск очереди пауз в App (miniapp-pause-c3a, §7.2).
// Без React-хуков и без хранилищ: всё состояние — в замыкании. Контекст — createContext без JSX.
// runPauseGate: true только при 'open'; иной результат и отказ промиса → false.
//   Таймаут уже внутри гейта c2 (pauseStartupGate), свой не добавляем.
// start: очередь уже есть → ничего; иначе makeQueue(dispatch) и tick, чтобы поднять слот после перезагрузки.
// stop необратим (метода start у очереди нет), поэтому следующий start создаёт новую очередь:
//   повторный запуск эффекта (mount → cleanup → mount) получает свежую очередь, старая остановлена.
// queue(): без очереди enqueue отклоняется Error('pause: no queue'), tick и resumeAuth ничего не делают.
// Исход очереди — только текущему слушателю; слушателя нет → исход отброшен (экран сам перечитает состояние).
// formDays (целое 1..7 или null) — только в памяти: не на устройстве и не в логе.

import { createContext } from 'react';

import type { PauseQueue, PauseQueueOutcome } from './pauseQueue.ts';
import type { PauseOpArgs, PauseOpKind, PauseQueueStore } from './pauseQueueStore.ts';

/** Гейт запуска; в App — pauseStartupGate из pauseQueue.ts. */
export type PauseGate = (store: PauseQueueStore, ownerId: string | null) => Promise<'open' | 'closed'>;

export type PauseOutcomeListener = (event: PauseQueueOutcome) => void;

export interface PauseRuntimeOptions {
  makeQueue(onOutcome: PauseOutcomeListener): PauseQueue;
  sendClosed(): boolean;
}

export interface PauseRuntime {
  start(): void;
  stop(): void;
  queue(): PauseQueue;
  attach(listener: PauseOutcomeListener): () => void;
  sendClosed(): boolean;
  getFormDays(): number | null;
  setFormDays(days: number | null): void;
}

export const PAUSE_NO_QUEUE_MESSAGE = 'pause: no queue';
export const PAUSE_FORM_DAYS_MIN = 1;
export const PAUSE_FORM_DAYS_MAX = 7;

/** true только при 'open'; любой другой результат и любой отказ → false. */
export async function runPauseGate(
  gate: PauseGate,
  store: PauseQueueStore,
  ownerId: string | null,
): Promise<boolean> {
  try {
    return (await gate(store, ownerId)) === 'open';
  } catch {
    return false;
  }
}

function isFormDays(days: number): boolean {
  return Number.isInteger(days) && days >= PAUSE_FORM_DAYS_MIN && days <= PAUSE_FORM_DAYS_MAX;
}

export function createPauseRuntime(options: PauseRuntimeOptions): PauseRuntime {
  let q: PauseQueue | null = null;
  let listener: PauseOutcomeListener | null = null;
  let formDays: number | null = null;

  function dispatch(event: PauseQueueOutcome): void {
    const current = listener;
    if (current !== null) current(event);
  }

  function start(): void {
    if (q !== null) return;
    const next = options.makeQueue(dispatch);
    q = next;
    void next.tick().catch(() => undefined);
  }

  function stop(): void {
    const current = q;
    q = null;
    if (current !== null) current.stop();
  }

  const facade: PauseQueue = {
    enqueue: (kind: PauseOpKind, args: PauseOpArgs) =>
      q === null ? Promise.reject(new Error(PAUSE_NO_QUEUE_MESSAGE)) : q.enqueue(kind, args),
    tick: () => (q === null ? Promise.resolve() : q.tick()),
    resumeAuth: () => {
      if (q !== null) q.resumeAuth();
    },
    stop,
  };

  return {
    start,
    stop,
    queue: () => facade,
    attach: (next: PauseOutcomeListener) => {
      listener = next;
      return () => {
        if (listener === next) listener = null;
      };
    },
    sendClosed: () => options.sendClosed(),
    getFormDays: () => formDays,
    setFormDays: (days: number | null) => {
      formDays = days !== null && isFormDays(days) ? days : null;
    },
  };
}

/** Рантайм пауз фазы app; null — вне фазы app. */
export const PauseRuntimeContext = createContext<PauseRuntime | null>(null);
