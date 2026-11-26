// apps/miniapp/src/components/pauseRuntime.test.ts — vitest, environment node, без DOM (miniapp-pause-c3a §9).
// Очередь фейковая: считаем вызовы, сеть и хранилище не трогаем.
import { describe, expect, it } from 'vitest';

import type { PauseQueue, PauseQueueOutcome } from './pauseQueue.ts';
import type { PauseQueueStore } from './pauseQueueStore.ts';
import { createPauseRuntime, runPauseGate, type PauseGate } from './pauseRuntime.ts';

interface FakeQueue extends PauseQueue {
  calls: { enqueue: number; tick: number; resumeAuth: number; stop: number };
}

type Emit = (event: PauseQueueOutcome) => void;

const WIPED: PauseQueueOutcome = { type: 'wiped' };
const DONE: PauseQueueOutcome = { type: 'done', kind: 'request', result: null };

function fakeQueue(): FakeQueue {
  const calls = { enqueue: 0, tick: 0, resumeAuth: 0, stop: 0 };
  return {
    calls,
    enqueue: async () => {
      calls.enqueue += 1;
      return 'op-1';
    },
    tick: async () => {
      calls.tick += 1;
    },
    resumeAuth: () => {
      calls.resumeAuth += 1;
    },
    stop: () => {
      calls.stop += 1;
    },
  };
}

function setup() {
  const queues: FakeQueue[] = [];
  const emits: Emit[] = [];
  const runtime = createPauseRuntime({
    makeQueue: (onOutcome) => {
      const q = fakeQueue();
      queues.push(q);
      emits.push(onOutcome);
      return q;
    },
    sendClosed: () => false,
  });
  return { runtime, queues, emits };
}

function nth<T>(list: T[], i: number): T {
  const item = list[i];
  if (item === undefined) throw new Error(`нет элемента ${i}`);
  return item;
}

function fakeStore(closed: boolean): { store: PauseQueueStore; sendClosedCalls: () => number } {
  let calls = 0;
  const store: PauseQueueStore = {
    read: async () => null,
    write: async () => true,
    claimOwner: async () => 'same' as const,
    clear: async () => undefined,
    setWipePending: async () => undefined,
    isWipePending: async () => false,
    wipeAll: async () => 'done' as const,
    sendClosed: () => {
      calls += 1;
      return closed;
    },
  };
  return { store, sendClosedCalls: () => calls };
}

describe('createPauseRuntime: start / stop', () => {
  it('start → makeQueue 1 раз и tick 1 раз; повторный start не создаёт новую очередь', () => {
    const { runtime, queues } = setup();
    runtime.start();
    expect(queues).toHaveLength(1);
    expect(nth(queues, 0).calls.tick).toBe(1);
    runtime.start();
    expect(queues).toHaveLength(1);
    expect(nth(queues, 0).calls.tick).toBe(1);
  });

  it('stop → q.stop; start после stop создаёт новую очередь', () => {
    const { runtime, queues } = setup();
    runtime.start();
    runtime.stop();
    expect(nth(queues, 0).calls.stop).toBe(1);
    runtime.start();
    expect(queues).toHaveLength(2);
    expect(nth(queues, 1).calls.tick).toBe(1);
    expect(nth(queues, 1).calls.stop).toBe(0);
    expect(nth(queues, 0).calls.stop).toBe(1);
  });

  it('mount → cleanup → mount: вызовы идут в новую очередь, старая остановлена', async () => {
    const { runtime, queues } = setup();
    runtime.start();
    runtime.stop();
    runtime.start();
    await runtime.queue().enqueue('cancel', { pause_id: 1 });
    expect(nth(queues, 0).calls.enqueue).toBe(0);
    expect(nth(queues, 1).calls.enqueue).toBe(1);
  });

  it('stop без start не бросает и очередь не создаёт', () => {
    const { runtime, queues } = setup();
    expect(() => runtime.stop()).not.toThrow();
    expect(queues).toHaveLength(0);
  });
});

describe('createPauseRuntime: queue()', () => {
  it('без start: enqueue отклоняется; tick и resumeAuth не бросают', async () => {
    const { runtime, queues } = setup();
    await expect(runtime.queue().enqueue('request', { days: 3, start_date: '2026-12-01' })).rejects.toThrow(
      'pause: no queue',
    );
    await expect(runtime.queue().tick()).resolves.toBeUndefined();
    expect(() => runtime.queue().resumeAuth()).not.toThrow();
    expect(queues).toHaveLength(0);
  });

  it('после start вызовы уходят в очередь', async () => {
    const { runtime, queues } = setup();
    runtime.start();
    await expect(runtime.queue().enqueue('cancel', { pause_id: 7 })).resolves.toBe('op-1');
    await runtime.queue().tick();
    runtime.queue().resumeAuth();
    const q = nth(queues, 0);
    expect(q.calls.enqueue).toBe(1);
    expect(q.calls.tick).toBe(2);
    expect(q.calls.resumeAuth).toBe(1);
  });

  it('после stop enqueue снова отклоняется', async () => {
    const { runtime } = setup();
    runtime.start();
    runtime.stop();
    await expect(runtime.queue().enqueue('resume', { pause_id: 2 })).rejects.toThrow('pause: no queue');
  });

  it('queue().stop останавливает очередь; следующий start создаёт новую', () => {
    const { runtime, queues } = setup();
    runtime.start();
    runtime.queue().stop();
    expect(nth(queues, 0).calls.stop).toBe(1);
    runtime.start();
    expect(queues).toHaveLength(2);
  });
});

describe('createPauseRuntime: attach / detach', () => {
  it('исход приходит текущему listener, после detach — не приходит', () => {
    const { runtime, emits } = setup();
    runtime.start();
    const got: PauseQueueOutcome[] = [];
    const detach = runtime.attach((event) => {
      got.push(event);
    });
    nth(emits, 0)(WIPED);
    expect(got).toEqual([WIPED]);
    detach();
    nth(emits, 0)(DONE);
    expect(got).toEqual([WIPED]);
  });

  it('новый listener заменяет прежний; старый detach нового не снимает', () => {
    const { runtime, emits } = setup();
    runtime.start();
    const a: PauseQueueOutcome[] = [];
    const b: PauseQueueOutcome[] = [];
    const detachA = runtime.attach((event) => {
      a.push(event);
    });
    runtime.attach((event) => {
      b.push(event);
    });
    nth(emits, 0)(DONE);
    detachA();
    nth(emits, 0)(WIPED);
    expect(a).toEqual([]);
    expect(b).toEqual([DONE, WIPED]);
  });

  it('без listener исход отбрасывается без ошибки', () => {
    const { runtime, emits } = setup();
    runtime.start();
    expect(() => nth(emits, 0)(WIPED)).not.toThrow();
  });
});

describe('runPauseGate', () => {
  it("'open' → true; гейт получает store и ownerId", async () => {
    const { store } = fakeStore(false);
    const seen: unknown[] = [];
    const gate: PauseGate = async (s, owner) => {
      seen.push(s, owner);
      return 'open';
    };
    await expect(runPauseGate(gate, store, '42')).resolves.toBe(true);
    expect(seen).toEqual([store, '42']);
  });

  it('иной результат → false', async () => {
    const { store } = fakeStore(false);
    await expect(runPauseGate(async () => 'closed', store, '42')).resolves.toBe(false);
    await expect(runPauseGate(async () => 'unexpected' as unknown as 'closed', store, '42')).resolves.toBe(false);
  });

  it('отказ промиса → false', async () => {
    const { store } = fakeStore(false);
    const rejecting: PauseGate = async () => {
      throw new Error('gate failed');
    };
    const throwing: PauseGate = () => {
      throw new Error('sync');
    };
    await expect(runPauseGate(rejecting, store, '42')).resolves.toBe(false);
    await expect(runPauseGate(throwing, store, null)).resolves.toBe(false);
  });
});

describe('createPauseRuntime: formDays и sendClosed', () => {
  it('formDays: set и get, сброс null', () => {
    const { runtime } = setup();
    expect(runtime.getFormDays()).toBeNull();
    runtime.setFormDays(3);
    expect(runtime.getFormDays()).toBe(3);
    runtime.setFormDays(7);
    expect(runtime.getFormDays()).toBe(7);
    runtime.setFormDays(null);
    expect(runtime.getFormDays()).toBeNull();
  });

  it('formDays вне 1..7 или дробное → null', () => {
    const { runtime } = setup();
    for (const bad of [0, 8, 2.5, -1, Number.NaN]) {
      runtime.setFormDays(5);
      runtime.setFormDays(bad);
      expect(runtime.getFormDays()).toBeNull();
    }
  });

  it('sendClosed передаёт вызов store', () => {
    for (const closed of [true, false]) {
      const { store, sendClosedCalls } = fakeStore(closed);
      const runtime = createPauseRuntime({ makeQueue: () => fakeQueue(), sendClosed: () => store.sendClosed() });
      expect(runtime.sendClosed()).toBe(closed);
      expect(sendClosedCalls()).toBe(1);
    }
  });
});
