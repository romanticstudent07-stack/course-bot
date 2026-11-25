// apps/miniapp/src/components/pauseSend.ts — отправитель очереди пауз (miniapp-pause-c1, T5-C1).
// Единственное место вызова трёх POST /pause/* (t5-bc §5): request, cancel, resume.
// args и opId слота уходят как есть; ошибку не ловим — её разбирает воркер pauseQueue.ts (B2).
// buildPauseQueueDeps собирает зависимости для createPauseQueue; запуск воркера — C2/C3.
// В main модуль никто не вызывает.

import {
  newClientOpId,
  postPauseCancel,
  postPauseRequest,
  postPauseResume,
  readTgUserId,
  type PauseRequestBody,
  type PauseTargetBody,
} from '../api/client.ts';
import type { PauseLockManager, PauseQueueDeps, PauseQueueOutcome } from './pauseQueue.ts';
import type { PauseQueueStore, PauseSlot } from './pauseQueueStore.ts';

/** Отправка слота: вид операции → свой POST с opId слота как X-Client-Op-Id. */
export function sendPauseOp(slot: PauseSlot): Promise<unknown> {
  switch (slot.kind) {
    case 'request':
      return postPauseRequest(slot.args as PauseRequestBody, slot.opId);
    case 'cancel':
      return postPauseCancel(slot.args as PauseTargetBody, slot.opId);
    case 'resume':
      return postPauseResume(slot.args as PauseTargetBody, slot.opId);
  }
}

/** tg_user_id из initData строкой — владелец слота; нет → null. */
export function pauseOwnerId(): string | null {
  const id = readTgUserId();
  return id === null ? null : String(id);
}

function pauseLocks(): PauseLockManager | null {
  const nav = (globalThis as { navigator?: { locks?: unknown } }).navigator;
  const locks = nav?.locks;
  return locks && typeof (locks as PauseLockManager).request === 'function' ? (locks as PauseLockManager) : null;
}

export function buildPauseQueueDeps(opts: {
  store: PauseQueueStore;
  onOutcome(event: PauseQueueOutcome): void;
}): PauseQueueDeps {
  return {
    store: opts.store,
    send: sendPauseOp,
    getOwnerId: pauseOwnerId,
    now: () => Date.now(),
    newOpId: newClientOpId,
    schedule: (fn, ms) => {
      const id = setTimeout(fn, ms);
      return () => clearTimeout(id);
    },
    locks: pauseLocks(),
    onOutcome: opts.onOutcome,
  };
}
