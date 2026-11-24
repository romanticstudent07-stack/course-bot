// Тесты воркера очереди пауз (miniapp-pause-b2, T5-B2): фейковые store, lock, часы, schedule и send.

import { describe, expect, it } from 'vitest';

import { ApiError } from '../api/client.ts';
import {
  PAUSE_CONFLICT_TEXT,
  createPauseQueue,
  pauseBackoffMs,
  type PauseLockManager,
  type PauseQueueOutcome,
} from './pauseQueue.ts';
import type { PauseQueueStore, PauseSlot } from './pauseQueueStore.ts';

const T0 = 1_800_000_000_000;
const ARGS = { days: 3, start_date: '2026-12-01' };

interface FakeStore extends PauseQueueStore {
  slot: PauseSlot | null;
  wipePending: boolean;
  wipeCalls: number;
}

/** Один слот на store; read отдаёт его как есть — так видна чужая запись (гейт владельца). */
function fakeStore(): FakeStore {
  const s: FakeStore = {
    slot: null,
    wipePending: false,
    wipeCalls: 0,
    read: async () => (s.slot ? { ...s.slot } : null),
    write: async (slot) => {
      s.slot = { ...slot };
    },
    clear: async () => {
      s.slot = null;
    },
    setWipePending: async () => {
      s.wipePending = true;
    },
    isWipePending: async () => s.wipePending,
    wipeAll: async () => {
      s.wipeCalls += 1;
      s.slot = null;
      s.wipePending = false;
      return 'done';
    },
    sendClosed: () => false,
  };
  return s;
}

function fakeLocks(busy: boolean): PauseLockManager & { calls: number } {
  const m = {
    calls: 0,
    request<T>(_name: string, _opts: { ifAvailable: true }, cb: (lock: unknown) => Promise<T>): Promise<T> {
      m.calls += 1;
      return cb(busy ? null : {});
    },
  };
  return m;
}

interface Harness {
  store: FakeStore;
  sent: PauseSlot[];
  outcomes: PauseQueueOutcome[];
  timers: number[];
  clock: { t: number };
  owner: { id: string | null };
  replies: Array<() => Promise<unknown>>;
  queue: ReturnType<typeof createPauseQueue>;
  newWorker(): ReturnType<typeof createPauseQueue>;
}

function harness(opts: { store?: FakeStore; locks?: PauseLockManager | null } = {}): Harness {
  const store = opts.store ?? fakeStore();
  const sent: PauseSlot[] = [];
  const outcomes: PauseQueueOutcome[] = [];
  const timers: number[] = [];
  const clock = { t: T0 };
  const owner: { id: string | null } = { id: 'A' };
  const replies: Array<() => Promise<unknown>> = [];
  let ids = 0;
  const make = () =>
    createPauseQueue({
      store,
      send: async (slot) => {
        sent.push({ ...slot });
        const next = replies.shift();
        return next ? next() : { status: 201 };
      },
      getOwnerId: () => owner.id,
      now: () => clock.t,
      newOpId: () => `op-${++ids}`,
      schedule: (_fn, ms) => {
        timers.push(ms);
        return () => undefined;
      },
      locks: opts.locks === undefined ? null : opts.locks,
      onOutcome: (e) => outcomes.push(e),
    });
  return { store, sent, outcomes, timers, clock, owner, replies, queue: make(), newWorker: make };
}

const fail = (err: unknown) => () => Promise.reject(err);

describe('pauseQueue', () => {
  it('регрессия 1: сеть → 429 Retry-After 5 → повтор не раньше 5 с тем же opId и args; новый воркер тоже', async () => {
    const h = harness();
    const opId = await h.queue.enqueue('request', ARGS);
    h.replies.push(fail(new TypeError('Failed to fetch')));
    await h.queue.tick();
    expect(h.store.slot).toMatchObject({ phase: 'uncertain', attempt: 1, notBefore: T0 + 2000 });

    h.clock.t = T0 + 2000;
    h.replies.push(fail(new ApiError(429, 'RATE_LIMITED', 'slow down', 5)));
    await h.queue.tick();
    expect(h.store.slot).toMatchObject({ attempt: 2, notBefore: T0 + 7000 });

    h.clock.t = T0 + 6999;
    await h.queue.tick();
    expect(h.sent).toHaveLength(2);
    expect(h.timers[h.timers.length - 1]).toBe(1);

    const fresh = h.newWorker();
    await fresh.tick();
    expect(h.sent).toHaveLength(2);

    h.clock.t = T0 + 7000;
    await fresh.tick();
    expect(h.sent).toHaveLength(3);
    for (const s of h.sent) {
      expect(s.opId).toBe(opId);
      expect(s.args).toEqual(ARGS);
      expect(s.kind).toBe('request');
    }
    expect(h.store.slot).toBeNull();
    expect(h.outcomes).toEqual([{ type: 'done', kind: 'request', result: { status: 201 } }]);
  });

  it('backoff 2, 4, 8 … 60 с, потолок держится', async () => {
    expect([0, 1, 2, 3, 4, 5, 6, 10].map(pauseBackoffMs)).toEqual([
      2000, 4000, 8000, 16000, 32000, 60000, 60000, 60000,
    ]);
    const h = harness();
    await h.queue.enqueue('cancel', { pause_id: 7 });
    const delays: number[] = [];
    for (let i = 0; i < 7; i += 1) {
      h.replies.push(fail(new ApiError(503, 'SERVICE_UNAVAILABLE', 'down')));
      await h.queue.tick();
      const slot = h.store.slot as PauseSlot;
      delays.push(slot.notBefore - h.clock.t);
      h.clock.t = slot.notBefore;
    }
    expect(delays).toEqual([2000, 4000, 8000, 16000, 32000, 60000, 60000]);
    expect(new Set(h.sent.map((s) => s.opId)).size).toBe(1);
  });

  it('201 → слот очищен, onOutcome done', async () => {
    const h = harness();
    await h.queue.enqueue('resume', { pause_id: 3 });
    h.replies.push(() => Promise.resolve({ id: 3 }));
    await h.queue.tick();
    expect(h.store.slot).toBeNull();
    expect(h.outcomes).toEqual([{ type: 'done', kind: 'resume', result: { id: 3 } }]);
  });

  it('409 IDEMPOTENCY_CONFLICT → wipePending, send больше не вызывается, текст R339 дословно', async () => {
    const h = harness();
    await h.queue.enqueue('request', ARGS);
    h.replies.push(fail(new ApiError(409, 'IDEMPOTENCY_CONFLICT', 'conflict')));
    await h.queue.tick();
    expect(h.store.wipePending).toBe(true);
    expect(h.outcomes).toEqual([{ type: 'conflict', text: 'локальные данные повреждены; переоткройте Mini App' }]);
    expect(PAUSE_CONFLICT_TEXT).toBe('локальные данные повреждены; переоткройте Mini App');
    await h.queue.enqueue('request', ARGS);
    await h.queue.tick();
    expect(h.sent).toHaveLength(1);
  });

  it.each(['PAUSE_ALREADY_OPEN', 'PAUSE_REFUSED', 'PAUSE_NOT_CANCELLABLE', 'PAUSE_NOT_ACTIVE'])(
    'бизнес-409 %s → слот очищен, wipeAll не вызван',
    async (code) => {
      const h = harness();
      await h.queue.enqueue('request', ARGS);
      h.replies.push(fail(new ApiError(409, code, 'refused')));
      await h.queue.tick();
      expect(h.store.slot).toBeNull();
      expect(h.store.wipeCalls).toBe(0);
      expect(h.store.wipePending).toBe(false);
      expect(h.outcomes).toEqual([{ type: 'business', code }]);
    },
  );

  it.each<[number, string]>([
    [404, 'PAUSE_NOT_FOUND'],
    [422, 'VALIDATION_ERROR'],
    [409, 'SOMETHING_ELSE'],
  ])('%i %s → stopped, повтора нет', async (status, code) => {
    const h = harness();
    await h.queue.enqueue('request', ARGS);
    h.replies.push(fail(new ApiError(status, code, 'no')));
    await h.queue.tick();
    expect(h.store.slot?.phase).toBe('stopped');
    expect(h.outcomes).toEqual([{ type: 'stopped', status, code }]);
    h.clock.t += 120_000;
    await h.queue.tick();
    expect(h.sent).toHaveLength(1);
    expect(h.timers).toEqual([]);
  });

  it('tick при stopped send не вызывает', async () => {
    const store = fakeStore();
    store.slot = {
      ownerId: 'A', kind: 'request', args: ARGS, opId: 'old', phase: 'stopped', attempt: 0, notBefore: 0, savedAt: T0,
    };
    const h = harness({ store });
    await h.queue.tick();
    expect(h.sent).toEqual([]);
    expect(h.outcomes).toEqual([]);
  });

  it('enqueue при stopped даёт новый opId', async () => {
    const store = fakeStore();
    store.slot = {
      ownerId: 'A', kind: 'request', args: ARGS, opId: 'old', phase: 'stopped', attempt: 2, notBefore: 0, savedAt: T0,
    };
    const h = harness({ store });
    const opId = await h.queue.enqueue('request', { days: 2, start_date: '2026-12-02' });
    expect(opId).toBe('op-1');
    expect(h.store.slot).toMatchObject({ opId: 'op-1', phase: 'queued', attempt: 0, savedAt: T0 });
    await h.queue.tick();
    expect(h.sent.map((s) => s.opId)).toEqual(['op-1']);
  });

  it('401 → нет повтора до resumeAuth', async () => {
    const h = harness();
    await h.queue.enqueue('request', ARGS);
    h.replies.push(fail(new ApiError(401, 'TG_INIT_INVALID', 'auth')));
    await h.queue.tick();
    h.clock.t += 300_000;
    await h.queue.tick();
    expect(h.sent).toHaveLength(1);
    expect(h.outcomes).toEqual([]);
    h.queue.resumeAuth();
    await h.queue.tick();
    expect(h.sent).toHaveLength(2);
    expect(h.sent[1]?.opId).toBe(h.sent[0]?.opId);
    expect(h.store.slot).toBeNull();
  });

  it('смена владельца → wipeAll до send', async () => {
    const h = harness();
    await h.queue.enqueue('request', ARGS);
    h.owner.id = 'B';
    await h.queue.tick();
    expect(h.store.wipeCalls).toBe(1);
    expect(h.sent).toEqual([]);
    expect(h.store.slot).toBeNull();
  });

  it('lock занят (ifAvailable → null) → send не вызван; без locks — send вызван', async () => {
    const busy = fakeLocks(true);
    const h1 = harness({ locks: busy });
    await h1.queue.enqueue('request', ARGS);
    await h1.queue.tick();
    expect(busy.calls).toBe(1);
    expect(h1.sent).toEqual([]);
    expect(h1.store.slot?.phase).toBe('queued');

    const h2 = harness({ locks: null });
    await h2.queue.enqueue('request', ARGS);
    await h2.queue.tick();
    expect(h2.sent).toHaveLength(1);
  });

  it('enqueue при занятом слоте не меняет opId', async () => {
    const h = harness();
    const first = await h.queue.enqueue('request', ARGS);
    const second = await h.queue.enqueue('request', { days: 5, start_date: '2026-12-09' });
    expect(second).toBe(first);
    expect(h.store.slot?.args).toEqual(ARGS);
    h.replies.push(fail(new TypeError('timeout')));
    await h.queue.tick();
    expect(h.store.slot?.phase).toBe('uncertain');
    expect(await h.queue.enqueue('cancel', { pause_id: 1 })).toBe(first);
  });
});
