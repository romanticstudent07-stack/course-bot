// apps/miniapp/src/components/drafts.test.ts — vitest, environment node.
// DraftStore: сохранение/чтение, очистка при смене tg_user_id, TTL 24 ч, только step/email/city;
// метки finished на устройстве нет (returning-2): saveDraft / openDraft / finishDraft с finished
// → хранилище пусто; ошибка хранилища переход к курсу не блокирует.
// D-23 (miniapp-fix-1): withTimeout, очередь createSerialDraftStore, seal, таймауты openDraft / finishDraft.
import { describe, expect, it } from 'vitest';

import {
  CITY_OPTIONS,
  DRAFT_FUTURE_SKEW_MS,
  DRAFT_TTL_MS,
  EMAIL_MAX_LENGTH,
  EMPTY_DRAFT,
  createDraftStore,
  createMemoryDraftStore,
  createSerialDraftStore,
  finishDraft,
  openDraft,
  parseStoredDraft,
  sanitizeDraft,
  saveDraft,
  withTimeout,
  type Draft,
  type DraftStore,
  type StoredDraft,
} from './drafts.ts';

const NOW = Date.UTC(2026, 9, 2, 12, 0, 0);
const USER = 777;
const OTHER = 888;
const DRAFT: Draft = { step: 'city', email: 'a@example.com', city: CITY_OPTIONS[0] };

function validStored(over: Record<string, unknown> = {}): Record<string, unknown> {
  return { v: 1, tgUserId: USER, savedAt: NOW, ...DRAFT, ...over };
}

describe('сохранение и чтение', () => {
  it('сохранил → прочитал тот же черновик', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW);
    expect(await openDraft(store, USER, NOW + 1000)).toEqual(DRAFT);
  });

  it('пустое хранилище → null', async () => {
    expect(await openDraft(createMemoryDraftStore(), USER, NOW)).toBeNull();
  });

  it('в черновик попадают только step, email, city (+ v, tgUserId, savedAt)', async () => {
    const store = createMemoryDraftStore();
    const withExtra = { ...DRAFT, birthDate: '1990-05-17', birth_date: '1990-05-17' } as Draft;
    await saveDraft(store, USER, withExtra, NOW);
    const raw = store.peek() as Record<string, unknown>;
    expect(Object.keys(raw).sort()).toEqual(['city', 'email', 'savedAt', 'step', 'tgUserId', 'v']);
    expect(JSON.stringify(raw)).not.toContain('1990-05-17');
  });

  it('пользователь неизвестен → ничего не пишем', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, null, DRAFT, NOW);
    expect(store.peek()).toBeUndefined();
  });
});

describe('смена tg_user_id → полная очистка сразу', () => {
  it('другой пользователь не видит черновик, запись удалена', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW);
    expect(await openDraft(store, OTHER, NOW)).toBeNull();
    expect(store.peek()).toBeUndefined();
    // и первый пользователь его тоже больше не получит
    expect(await openDraft(store, USER, NOW)).toBeNull();
  });

  it('пользователь неизвестен → очистка', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW);
    expect(await openDraft(store, null, NOW)).toBeNull();
    expect(store.peek()).toBeUndefined();
  });
});

describe('TTL 24 ч', () => {
  it('ровно 24 ч — ещё на месте', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW);
    expect(await openDraft(store, USER, NOW + DRAFT_TTL_MS)).toEqual(DRAFT);
  });

  it('старше 24 ч → удалён при открытии', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW);
    expect(await openDraft(store, USER, NOW + DRAFT_TTL_MS + 1)).toBeNull();
    expect(store.peek()).toBeUndefined();
  });

  it('savedAt из будущего → битая запись, удалена', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW + 2 * DRAFT_FUTURE_SKEW_MS);
    expect(await openDraft(store, USER, NOW)).toBeNull();
    expect(store.peek()).toBeUndefined();
  });
});

describe('битые записи', () => {
  it('parseStoredDraft: верная запись', () => {
    expect(parseStoredDraft(validStored())).toEqual(validStored());
  });

  it('parseStoredDraft: всё неверное → null', () => {
    const bad: unknown[] = [
      undefined,
      null,
      'x',
      42,
      validStored({ v: 2 }),
      validStored({ tgUserId: 0 }),
      validStored({ tgUserId: '777' }),
      validStored({ savedAt: 'now' }),
      validStored({ step: 'payment' }),
      validStored({ step: 'photo' }),
      validStored({ email: 5 }),
      validStored({ email: 'a'.repeat(EMAIL_MAX_LENGTH + 1) }),
      validStored({ city: 'Атлантида' }),
    ];
    for (const raw of bad) expect(parseStoredDraft(raw)).toBeNull();
  });

  it('битая запись в хранилище → очистка и null', async () => {
    let cleared = false;
    const store: DraftStore = {
      get: async () => ({ v: 1, tgUserId: USER, savedAt: NOW, step: 'payment', email: '', city: '' }),
      put: async () => undefined,
      clear: async () => {
        cleared = true;
      },
    };
    expect(await openDraft(store, USER, NOW)).toBeNull();
    expect(cleared).toBe(true);
  });

  it('sanitizeDraft: неизвестный город и шаг сбрасываются', () => {
    const dirty = { step: 'payment', email: 'x@y.z', city: 'Атлантида' } as unknown as Draft;
    expect(sanitizeDraft(dirty)).toEqual({ step: 'offer', email: 'x@y.z', city: '' });
    expect(sanitizeDraft(EMPTY_DRAFT)).toEqual(EMPTY_DRAFT);
  });
});

describe('метки finished на устройстве нет', () => {
  it('saveDraft со step finished → хранилище пусто (email и город стёрты)', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW - 5000);
    await saveDraft(store, USER, { ...DRAFT, step: 'finished' }, NOW);
    expect(store.peek()).toBeUndefined();
  });

  it('saveDraft со step finished и неизвестным пользователем → put не вызван, хранилище пусто', async () => {
    let putCalled = false;
    let cleared = false;
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => {
        putCalled = true;
      },
      clear: async () => {
        cleared = true;
      },
    };
    await saveDraft(store, null, { ...DRAFT, step: 'finished' }, NOW);
    expect(putCalled).toBe(false);
    expect(cleared).toBe(true);
  });

  it('openDraft со старой записью step finished → null и хранилище пусто', async () => {
    const store = createMemoryDraftStore();
    await store.put({ v: 1, tgUserId: USER, savedAt: NOW, step: 'finished', email: '', city: '' });
    expect(await openDraft(store, USER, NOW + 1000)).toBeNull();
    expect(store.peek()).toBeUndefined();
  });
});

describe('finishDraft', () => {
  it('известный пользователь с email и городом → хранилище пусто; onFinish 1 раз после очистки', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW - 5000);
    let calls = 0;
    let seenAtFinish: unknown = 'not-called';
    const onFinish = () => {
      calls += 1;
      seenAtFinish = store.peek();
    };
    await finishDraft(store, USER, NOW, onFinish);
    expect(store.peek()).toBeUndefined();
    expect(seenAtFinish).toBeUndefined();
    expect(calls).toBe(1);
  });

  it('после finishDraft следующее открытие → null (черновика нет)', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW - 5000);
    await finishDraft(store, USER, NOW, () => undefined);
    expect(await openDraft(store, USER, NOW + 1000)).toBeNull();
  });

  it('известный пользователь → put не вызван, clear вызван', async () => {
    let putCalled = false;
    let cleared = false;
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => {
        putCalled = true;
      },
      clear: async () => {
        cleared = true;
      },
    };
    await finishDraft(store, USER, NOW, () => undefined);
    expect(putCalled).toBe(false);
    expect(cleared).toBe(true);
  });

  it('clear возвращает reject → finishDraft резолвится, onFinish 1 раз', async () => {
    let calls = 0;
    const onFinish = () => {
      calls += 1;
    };
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => undefined,
      clear: async () => {
        throw new Error('clear failed');
      },
    };
    await expect(finishDraft(store, USER, NOW, onFinish)).resolves.toBeUndefined();
    expect(calls).toBe(1);
  });

  it('clear бросает синхронно → finishDraft резолвится, onFinish 1 раз', async () => {
    let calls = 0;
    const onFinish = () => {
      calls += 1;
    };
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => undefined,
      clear: () => {
        throw new Error('clear failed sync');
      },
    };
    await expect(finishDraft(store, USER, NOW, onFinish)).resolves.toBeUndefined();
    expect(calls).toBe(1);
  });

  it('tgUserId неизвестен → clear вызван, put не вызван, onFinish 1 раз', async () => {
    let calls = 0;
    const onFinish = () => {
      calls += 1;
    };
    let cleared = false;
    let putCalled = false;
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => {
        putCalled = true;
      },
      clear: async () => {
        cleared = true;
      },
    };
    await finishDraft(store, null, NOW, onFinish);
    expect(cleared).toBe(true);
    expect(putCalled).toBe(false);
    expect(calls).toBe(1);
  });

  it('tgUserId неизвестен и clear возвращает reject → finishDraft резолвится, onFinish 1 раз', async () => {
    let calls = 0;
    const onFinish = () => {
      calls += 1;
    };
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => undefined,
      clear: async () => {
        throw new Error('clear failed');
      },
    };
    await expect(finishDraft(store, null, NOW, onFinish)).resolves.toBeUndefined();
    expect(calls).toBe(1);
  });
});

// ---- D-23 (miniapp-fix-1) ----

const STORED: StoredDraft = { v: 1, tgUserId: USER, savedAt: NOW, ...DRAFT };

/** Дать отработать микрозадачам и таймерам 0 мс. */
function tick(): Promise<void> {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

function sleep(ms: number): Promise<void> {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

/** Память + журнал вызовов; put пишет только после release(). */
function gatedStore() {
  const mem = createMemoryDraftStore();
  const calls: string[] = [];
  let releasePut: (() => void) | null = null;
  const inner: DraftStore = {
    get: () => {
      calls.push('get');
      return mem.get();
    },
    put: (value) => {
      calls.push('put');
      return new Promise<void>((resolve) => {
        releasePut = () => {
          void mem.put(value).then(resolve);
        };
      });
    },
    clear: () => {
      calls.push('clear');
      return mem.clear();
    },
  };
  return {
    mem,
    calls,
    inner,
    release: () => {
      if (releasePut !== null) releasePut();
    },
  };
}

describe('withTimeout', () => {
  it('быстрое p → значение', async () => {
    await expect(withTimeout(Promise.resolve(5), 50, 0)).resolves.toBe(5);
  });

  it('медленное p → fallback', async () => {
    const never = new Promise<number>(() => undefined);
    await expect(withTimeout(never, 20, 0)).resolves.toBe(0);
  });

  it('reject до таймаута → reject', async () => {
    await expect(withTimeout(Promise.reject(new Error('boom')), 50, 0)).rejects.toThrow('boom');
  });

  it('reject после таймаута → fallback, ошибка проглочена', async () => {
    const late = new Promise<number>((_resolve, reject) => {
      setTimeout(() => reject(new Error('late')), 40);
    });
    await expect(withTimeout(late, 20, 0)).resolves.toBe(0);
    await sleep(50);
  });
});

describe('очередь хранилища (createSerialDraftStore)', () => {
  it('put (держим) → clear: clear ждёт put, хранилище пусто, порядок put, clear', async () => {
    const g = gatedStore();
    const store = createSerialDraftStore(g.inner, 1000);
    const p1 = store.put(STORED);
    const p2 = store.clear();
    await tick();
    expect(g.calls).toEqual(['put']);
    g.release();
    await Promise.all([p1, p2]);
    expect(g.calls).toEqual(['put', 'clear']);
    expect(g.mem.peek()).toBeUndefined();
  });

  it('зависший get → следующий put выполняется после timeoutMs', async () => {
    const mem = createMemoryDraftStore();
    const inner: DraftStore = {
      get: () => new Promise<unknown>(() => undefined),
      put: (value) => mem.put(value),
      clear: () => mem.clear(),
    };
    const store = createSerialDraftStore(inner, 30);
    const started = Date.now();
    void store.get();
    const put = store.put(STORED);
    await tick();
    expect(mem.peek()).toBeUndefined();
    await put;
    expect(mem.peek()).toEqual(STORED);
    expect(Date.now() - started).toBeGreaterThanOrEqual(20);
  });

  it('reject и синхронный throw inner очередь не ломают', async () => {
    let clears = 0;
    const inner: DraftStore = {
      get: async () => {
        throw new Error('get failed');
      },
      put: () => {
        throw new Error('put failed sync');
      },
      clear: async () => {
        clears += 1;
      },
    };
    const store = createSerialDraftStore(inner, 50);
    await expect(store.get()).rejects.toThrow('get failed');
    await expect(store.put(STORED)).rejects.toThrow('put failed sync');
    await expect(store.clear()).resolves.toBeUndefined();
    expect(clears).toBe(1);
  });
});

describe('seal', () => {
  it('put после seal → inner.put не вызван; get и clear работают; повторный seal безвреден', async () => {
    const g = gatedStore();
    const store = createSerialDraftStore(g.inner, 50);
    store.seal?.();
    await expect(store.put(STORED)).resolves.toBeUndefined();
    expect(g.calls).toEqual([]);
    store.seal?.();
    await expect(store.get()).resolves.toBeUndefined();
    await expect(store.clear()).resolves.toBeUndefined();
    expect(g.calls).toEqual(['get', 'clear']);
    expect(g.mem.peek()).toBeUndefined();
  });

  it('put, поставленный до seal и ещё не начатый, тоже не пишет', async () => {
    const g = gatedStore();
    const store = createSerialDraftStore(g.inner, 1000);
    const first = store.put(STORED);
    await tick();
    const second = store.put({ ...STORED, city: CITY_OPTIONS[1] });
    store.seal?.();
    g.release();
    await Promise.all([first, second]);
    expect(g.calls).toEqual(['put']);
    expect(g.mem.peek()).toEqual(STORED);
  });
});

describe('таймауты openDraft и finishDraft', () => {
  it('openDraft: зависший get → null за timeoutMs', async () => {
    const store: DraftStore = {
      get: () => new Promise<unknown>(() => undefined),
      put: async () => undefined,
      clear: async () => undefined,
    };
    await expect(openDraft(store, USER, NOW, 30)).resolves.toBeNull();
  });

  it('finishDraft: зависший clear → резолвится, onFinish 1 раз', async () => {
    let calls = 0;
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => undefined,
      clear: () => new Promise<void>(() => undefined),
    };
    await expect(
      finishDraft(store, USER, NOW, () => {
        calls += 1;
      }, 30),
    ).resolves.toBeUndefined();
    expect(calls).toBe(1);
  });

  it('после finishDraft saveDraft не пишет (очередь поверх памяти)', async () => {
    const mem = createMemoryDraftStore();
    const store = createSerialDraftStore(mem, 50);
    await finishDraft(store, USER, NOW, () => undefined, 50);
    await saveDraft(store, USER, DRAFT, NOW);
    expect(mem.peek()).toBeUndefined();
  });

  it('saveDraft, поставленный прямо перед finishDraft, не возвращает email и город', async () => {
    const mem = createMemoryDraftStore();
    await mem.put(STORED);
    const store = createSerialDraftStore(mem, 50);
    const pending = saveDraft(store, USER, { ...DRAFT, city: CITY_OPTIONS[1] }, NOW);
    await finishDraft(store, USER, NOW, () => undefined, 50);
    await pending;
    expect(mem.peek()).toBeUndefined();
  });

  it('createDraftStore() в node (indexedDB нет) → у хранилища есть seal', () => {
    const store = createDraftStore();
    expect(typeof store.seal).toBe('function');
  });
});
