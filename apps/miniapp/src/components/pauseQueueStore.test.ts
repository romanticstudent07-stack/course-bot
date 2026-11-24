// apps/miniapp/src/components/pauseQueueStore.test.ts — vitest, без DOM и без библиотек (miniapp-pause-b1).
// Свой минимальный фейк IDBFactory: open, transaction, get / put / delete, deleteDatabase.
import { describe, expect, it } from 'vitest';

import {
  DRAFTS_DB_NAME,
  PAUSE_DB_NAME,
  PAUSE_SLOT_TTL_MS,
  createPauseQueueStore,
  type PauseSlot,
} from './pauseQueueStore.ts';

type Handler = (() => void) | null;

interface FakeReq {
  result: unknown;
  error: null;
  onsuccess: Handler;
  onerror: Handler;
  onblocked: Handler;
  onupgradeneeded: Handler;
}

function newReq(): FakeReq {
  return { result: undefined, error: null, onsuccess: null, onerror: null, onblocked: null, onupgradeneeded: null };
}

function createFakeIdb(blocked: string[] = []) {
  const dbs = new Map<string, Map<string, unknown>>();
  const deleted: string[] = [];
  const later = (fn: () => void) => setTimeout(fn, 0);

  const factory = {
    open(name: string) {
      const req = newReq();
      later(() => {
        const isNew = !dbs.has(name);
        if (isNew) dbs.set(name, new Map());
        const data = dbs.get(name) as Map<string, unknown>;
        let hasStore = !isNew;
        req.result = {
          objectStoreNames: { contains: () => hasStore },
          createObjectStore: () => {
            hasStore = true;
          },
          close: () => undefined,
          transaction: () => {
            const tx: { oncomplete: Handler; onerror: Handler; onabort: Handler; error: null; objectStore?: unknown } = {
              oncomplete: null,
              onerror: null,
              onabort: null,
              error: null,
            };
            const done = (result: unknown) => {
              later(() => tx.oncomplete?.());
              return { result };
            };
            tx.objectStore = () => ({
              get: (k: string) => done(data.has(k) ? structuredClone(data.get(k)) : undefined),
              put: (v: unknown, k: string) => {
                data.set(k, structuredClone(v));
                return done(k);
              },
              delete: (k: string) => {
                data.delete(k);
                return done(undefined);
              },
            });
            return tx;
          },
        };
        if (isNew) req.onupgradeneeded?.();
        req.onsuccess?.();
      });
      return req;
    },
    deleteDatabase(name: string) {
      deleted.push(name);
      const req = newReq();
      later(() => {
        if (blocked.includes(name)) {
          req.onblocked?.();
          return;
        }
        dbs.delete(name);
        req.onsuccess?.();
      });
      return req;
    },
  };
  return { factory: factory as unknown as IDBFactory, dbs, deleted };
}

const NOW = 1_800_000_000_000;

function slot(ownerId: string, over: Partial<PauseSlot> = {}): PauseSlot {
  return {
    ownerId,
    kind: 'request',
    args: { days: 3, start_date: '2026-12-01' },
    opId: 'op-' + ownerId,
    phase: 'queued',
    attempt: 0,
    notBefore: NOW,
    savedAt: NOW,
    ...over,
  };
}

describe('pauseQueueStore: IndexedDB (фейк)', () => {
  it('write → read тем же ownerId; чужой ownerId → null', async () => {
    const store = createPauseQueueStore(createFakeIdb().factory);
    await store.write(slot('A1'));
    expect(await store.read('A1', NOW + 1000)).toEqual(slot('A1'));
    expect(await store.read('A2', NOW + 1000)).toBeNull();
  });

  it('битая запись → null и запись удалена', async () => {
    const fake = createFakeIdb();
    fake.dbs.set(PAUSE_DB_NAME, new Map<string, unknown>([['slot:A1', { ownerId: 'A1', kind: 'bad' }]]));
    const store = createPauseQueueStore(fake.factory);
    expect(await store.read('A1', NOW)).toBeNull();
    expect(fake.dbs.get(PAUSE_DB_NAME)?.has('slot:A1')).toBe(false);
  });

  it('слот старше 24 ч → null и запись удалена', async () => {
    const fake = createFakeIdb();
    const store = createPauseQueueStore(fake.factory);
    await store.write(slot('A1'));
    expect(await store.read('A1', NOW + PAUSE_SLOT_TTL_MS + 1)).toBeNull();
    expect(fake.dbs.get(PAUSE_DB_NAME)?.has('slot:A1')).toBe(false);
  });

  it('clear удаляет только свой слот (завершение операции, R-2026-11-21)', async () => {
    const store = createPauseQueueStore(createFakeIdb().factory);
    await store.write(slot('A1'));
    await store.write(slot('A2', { kind: 'cancel', args: { pause_id: 7 } }));
    await store.clear('A1');
    expect(await store.read('A1', NOW)).toBeNull();
    expect(await store.read('A2', NOW)).toEqual(slot('A2', { kind: 'cancel', args: { pause_id: 7 } }));
  });

  it('setWipePending → isWipePending true, переживает новый экземпляр', async () => {
    const fake = createFakeIdb();
    const first = createPauseQueueStore(fake.factory);
    expect(await first.isWipePending()).toBe(false);
    await first.setWipePending();
    expect(await first.isWipePending()).toBe(true);
    expect(await createPauseQueueStore(fake.factory).isWipePending()).toBe(true);
  });

  it('wipeAll удаляет обе БД → done', async () => {
    const fake = createFakeIdb();
    const store = createPauseQueueStore(fake.factory);
    await store.setWipePending();
    expect(await store.wipeAll()).toBe('done');
    expect([...fake.deleted].sort()).toEqual([DRAFTS_DB_NAME, PAUSE_DB_NAME].sort());
    expect(store.sendClosed()).toBe(false);
    expect(fake.dbs.has(PAUSE_DB_NAME)).toBe(false);
  });

  it('onblocked у course-bot → blocked, sendClosed true, флаг остался', async () => {
    const fake = createFakeIdb([DRAFTS_DB_NAME]);
    const store = createPauseQueueStore(fake.factory);
    await store.setWipePending();
    expect(await store.wipeAll()).toBe('blocked');
    expect(store.sendClosed()).toBe(true);
    expect(await store.isWipePending()).toBe(true);
  });
});

describe('pauseQueueStore: idb = null → память', () => {
  it('те же операции работают', async () => {
    const store = createPauseQueueStore(null);
    await store.write(slot('A1'));
    expect(await store.read('A1', NOW)).toEqual(slot('A1'));
    expect(await store.read('A2', NOW)).toBeNull();
    expect(await store.read('A1', NOW + PAUSE_SLOT_TTL_MS + 1)).toBeNull();
    await store.write(slot('A1'));
    await store.clear('A1');
    expect(await store.read('A1', NOW)).toBeNull();
    await store.setWipePending();
    expect(await store.isWipePending()).toBe(true);
    expect(await store.wipeAll()).toBe('done');
    expect(await store.isWipePending()).toBe(false);
    expect(store.sendClosed()).toBe(false);
  });
});
