// apps/miniapp/src/components/drafts.test.ts — vitest, environment node.
// DraftStore: сохранение/чтение, очистка при смене tg_user_id, TTL 24 ч, только step/email/city;
// метки finished на устройстве нет (returning-2): saveDraft / openDraft / finishDraft с finished
// → хранилище пусто; ошибка хранилища переход к курсу не блокирует.
import { describe, expect, it } from 'vitest';

import {
  CITY_OPTIONS,
  DRAFT_FUTURE_SKEW_MS,
  DRAFT_TTL_MS,
  EMAIL_MAX_LENGTH,
  EMPTY_DRAFT,
  createMemoryDraftStore,
  finishDraft,
  openDraft,
  parseStoredDraft,
  sanitizeDraft,
  saveDraft,
  type Draft,
  type DraftStore,
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
