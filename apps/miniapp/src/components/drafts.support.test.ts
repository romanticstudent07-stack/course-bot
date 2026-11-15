// drafts.support.test.ts — черновик вопроса поддержки (miniapp-sup-1, Р-19): тема и текст,
// привязка к tg_user_id, 24 ч, обрезка, таймаут и ошибки хранилища.
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DRAFT_FUTURE_SKEW_MS,
  DRAFT_IO_TIMEOUT_MS,
  DRAFT_TTL_MS,
  EMPTY_SUPPORT_DRAFT,
  SUPPORT_DRAFT_MAX_CHARS,
  clearSupportDraft,
  createMemorySupportDraftStore,
  createSupportDraftStore,
  openSupportDraft,
  saveSupportDraft,
  type StoredSupportDraft,
  type SupportDraftStore,
} from './drafts.ts';

const NOW = 1_800_000_000_000;
const USER = 42;

function valid(): Record<string, unknown> {
  return { v: 1, tgUserId: USER, savedAt: NOW, topic: 's3', text: 'вопрос' };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('save → open', () => {
  it('тема и текст на месте; в записи v 1, tgUserId, savedAt', async () => {
    const store = createMemorySupportDraftStore();
    await saveSupportDraft(store, USER, { topic: 's3', text: 'вопрос' }, NOW);
    expect(store.peek()).toEqual({ v: 1, tgUserId: USER, savedAt: NOW, topic: 's3', text: 'вопрос' });
    expect(await openSupportDraft(store, USER, NOW + 1000)).toEqual({ topic: 's3', text: 'вопрос' });
  });

  it('тема без текста сохраняется', async () => {
    const store = createMemorySupportDraftStore();
    await saveSupportDraft(store, USER, { topic: 'other', text: '' }, NOW);
    expect(await openSupportDraft(store, USER, NOW)).toEqual({ topic: 'other', text: '' });
  });
});

describe('open: неподходящая запись → пустой черновик и запись стёрта', () => {
  const cases: Array<[string, Record<string, unknown>, number | null, number]> = [
    ['чужой tgUserId', valid(), USER + 1, NOW],
    ['tgUserId неизвестен', valid(), null, NOW],
    ['старше 24 ч', { ...valid(), savedAt: NOW - DRAFT_TTL_MS - 1 }, USER, NOW],
    ['savedAt в будущем', { ...valid(), savedAt: NOW + DRAFT_FUTURE_SKEW_MS + 1 }, USER, NOW],
    ['v 2', { ...valid(), v: 2 }, USER, NOW],
    ['тема не из списка', { ...valid(), topic: 's8' }, USER, NOW],
    ['текст не строка', { ...valid(), text: 123 }, USER, NOW],
  ];

  for (const [name, raw, tgUserId, now] of cases) {
    it(name, async () => {
      const store = createMemorySupportDraftStore();
      await store.put(raw as unknown as StoredSupportDraft);
      expect(await openSupportDraft(store, tgUserId, now)).toEqual(EMPTY_SUPPORT_DRAFT);
      expect(store.peek()).toBeUndefined();
    });
  }
});

describe('save', () => {
  it('пустой черновик → очистка', async () => {
    const store = createMemorySupportDraftStore();
    await saveSupportDraft(store, USER, { topic: 's1', text: 'текст' }, NOW);
    await saveSupportDraft(store, USER, { topic: null, text: '   ' }, NOW);
    expect(store.peek()).toBeUndefined();
  });

  it('tgUserId null → очистка', async () => {
    const store = createMemorySupportDraftStore();
    await saveSupportDraft(store, USER, { topic: 's1', text: 'текст' }, NOW);
    await saveSupportDraft(store, null, { topic: 's1', text: 'текст' }, NOW);
    expect(store.peek()).toBeUndefined();
  });

  it('текст 5000 знаков обрезан до 4000', async () => {
    const store = createMemorySupportDraftStore();
    await saveSupportDraft(store, USER, { topic: 's1', text: 'a'.repeat(5000) }, NOW);
    const stored = store.peek() as StoredSupportDraft;
    expect(stored.text).toHaveLength(SUPPORT_DRAFT_MAX_CHARS);
    expect(SUPPORT_DRAFT_MAX_CHARS).toBe(4000);
  });

  it('ошибка put глотается', async () => {
    const store: SupportDraftStore = {
      get: async () => undefined,
      put: () => Promise.reject(new Error('put failed')),
      clear: async () => undefined,
    };
    await expect(saveSupportDraft(store, USER, { topic: 's1', text: 'текст' }, NOW)).resolves.toBeUndefined();
  });
});

describe('open: хранилище не отвечает или падает', () => {
  it('get не завершается → пустой черновик через DRAFT_IO_TIMEOUT_MS', async () => {
    vi.useFakeTimers();
    const store: SupportDraftStore = {
      get: () => new Promise<unknown>(() => undefined),
      put: async () => undefined,
      clear: async () => undefined,
    };
    const p = openSupportDraft(store, USER, NOW);
    await vi.advanceTimersByTimeAsync(DRAFT_IO_TIMEOUT_MS);
    await expect(p).resolves.toEqual(EMPTY_SUPPORT_DRAFT);
  });

  it('get с ошибкой → пустой черновик без исключения', async () => {
    const store: SupportDraftStore = {
      get: () => Promise.reject(new Error('get failed')),
      put: async () => undefined,
      clear: async () => undefined,
    };
    await expect(openSupportDraft(store, USER, NOW)).resolves.toEqual(EMPTY_SUPPORT_DRAFT);
  });

  it('clear с ошибкой → clearSupportDraft не бросает', async () => {
    const store: SupportDraftStore = {
      get: async () => undefined,
      put: async () => undefined,
      clear: () => Promise.reject(new Error('clear failed')),
    };
    await expect(clearSupportDraft(store)).resolves.toBeUndefined();
  });
});

describe('createSupportDraftStore в node', () => {
  it('работает (память): save, open, clear', async () => {
    const store = createSupportDraftStore();
    await saveSupportDraft(store, USER, { topic: 's5', text: 'вопрос' }, NOW);
    expect(await openSupportDraft(store, USER, NOW)).toEqual({ topic: 's5', text: 'вопрос' });
    await clearSupportDraft(store);
    expect(await openSupportDraft(store, USER, NOW)).toEqual(EMPTY_SUPPORT_DRAFT);
  });
});
