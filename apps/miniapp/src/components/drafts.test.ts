// apps/miniapp/src/components/drafts.test.ts — vitest, environment node.
// DraftStore: сохранение/чтение, очистка при смене tg_user_id, TTL 24 ч, только step/email/city;
// finishDraft: после «Перейти к курсу» в черновике только метка finished, ошибка хранилища не блокирует.
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

describe('finishDraft', () => {
  it('сохранён черновик с email и городом → остаётся только метка finished; onFinish 1 раз после записи', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW - 5000);
    let calls = 0;
    let seenAtFinish: unknown = undefined;
    const onFinish = () => {
      calls += 1;
      seenAtFinish = store.peek();
    };
    await finishDraft(store, USER, NOW, onFinish);
    const expected = { v: 1, tgUserId: USER, savedAt: NOW, step: 'finished', email: '', city: '' };
    expect(store.peek()).toEqual(expected);
    expect(seenAtFinish).toEqual(expected);
    expect(calls).toBe(1);
    expect(JSON.stringify(store.peek())).not.toContain('a@example.com');
  });

  it('после finishDraft следующее открытие → экран finished без email и города', async () => {
    const store = createMemoryDraftStore();
    await saveDraft(store, USER, DRAFT, NOW - 5000);
    let calls = 0;
    const onFinish = () => {
      calls += 1;
    };
    await finishDraft(store, USER, NOW, onFinish);
    expect(await openDraft(store, USER, NOW + 1000)).toEqual({ step: 'finished', email: '', city: '' });
    expect(calls).toBe(1);
  });

  it('put возвращает reject → finishDraft резолвится, onFinish 1 раз', async () => {
    let calls = 0;
    const onFinish = () => {
      calls += 1;
    };
    const store: DraftStore = {
      get: async () => undefined,
      put: async () => {
        throw new Error('put failed');
      },
      clear: async () => undefined,
    };
    await expect(finishDraft(store, USER, NOW, onFinish)).resolves.toBeUndefined();
    expect(calls).toBe(1);
  });

  it('put бросает синхронно → finishDraft резолвится, onFinish 1 раз', async () => {
    let calls = 0;
    const onFinish = () => {
      calls += 1;
    };
    const store: DraftStore = {
      get: async () => undefined,
      put: () => {
        throw new Error('put failed sync');
      },
      clear: async () => undefined,
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
