// apps/miniapp/src/components/drafts.ts — черновик шагов после pid (1e-2, 1e-2b-2, returning-2, miniapp-fix-1,
// miniapp-i3-1a) и черновик вопроса поддержки (miniapp-sup-1).
//
// Нативный IndexedDB без библиотек, за интерфейсом DraftStore (в тестах — хранилище в памяти).
// Это ЕДИНСТВЕННЫЙ файл Mini App, который пишет на устройство.
//
// Правила (I4 §7 R380_cleanup, карточки 1e-2 §7, 1e-2b-2 §7, returning-2 §7.4):
//   - в черновике только step + служебные v, tgUserId, savedAt (miniapp-i3-1a, Р-16:
//     DRAFT_VERSION = 2; запись версии 1 не проходит parseStoredDraft → очистка, как битая).
//     Ответы анкеты сюда не класть НИКОГДА — они только в памяти экрана и уходят на сервер;
//     дату рождения — тоже (её нет в типе Draft; sanitizeDraft отбрасывает любые лишние поля).
//     short_no, status и reasons сервера — тоже нет;
//   - черновик привязан к tg_user_id: другой tg_user_id или неизвестный → полная
//     очистка сразу при открытии;
//   - черновик старше 24 ч (от последнего сохранения) → удалить при открытии;
//   - битая запись → удалить;
//   - метки finished на устройстве НЕТ (returning-2): «пройден ли онбординг» решает сервер
//     (GET /onboarding/status). Шаг 'finished' — это экран, а не хранимая метка:
//     saveDraft со step 'finished' → очистка; openDraft нашёл старую запись 'finished' →
//     очистка и null; «Перейти к курсу» (finishDraft) → очистка. Ошибка хранилища переход
//     не блокирует и в лог не пишется.
// D-23 (miniapp-fix-1): createDraftStore отдаёт хранилище с одной очередью get / put / clear
//   (операция держит очередь до своего завершения или 3 с); finishDraft вызывает seal() —
//   put после него не пишет; openDraft и finishDraft ждут хранилище не дольше 3 с (DRAFT_IO_TIMEOUT_MS).
// Шаги: offer → form → checkup → rules → finished. Анкета (шаг form) хранится на сервере
// (OnbForm.tsx), черновик на сервер не уходит.
// miniapp-sup-1: текст вопроса поддержки хранится по Р-19 (ключ support, 24 ч, привязка к tg_user_id);
//   ответы анкеты и Чек-Апа сюда не класть никогда. В записи только тема, текст и служебные
//   v, tgUserId, savedAt. Та же БД и то же хранилище объектов, что у шага онбординга; версия БД
//   и состав хранилищ не меняются. Своя очередь с таймаутом 3 с, без seal: finishDraft и seal
//   онбординга ключ support не трогают. Ошибки хранилища глотаются и в лог не пишутся.
import type { SupportTopicCode } from '../api/client.ts';

export const LATER_STEPS = ['offer', 'form', 'checkup', 'rules', 'finished'] as const;
export type LaterStep = (typeof LATER_STEPS)[number];

export interface Draft {
  step: LaterStep;
}

export const EMPTY_DRAFT: Draft = { step: 'offer' };

export const DRAFT_VERSION = 2;
export const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;
/** savedAt дальше этого в будущем — запись считается битой. */
export const DRAFT_FUTURE_SKEW_MS = 60 * 1000;
/** Сколько ждём хранилище в openDraft, finishDraft и в очереди (D-23). */
export const DRAFT_IO_TIMEOUT_MS = 3000;

export interface StoredDraft extends Draft {
  v: typeof DRAFT_VERSION;
  tgUserId: number;
  savedAt: number;
}

export interface DraftStore {
  /** Сырая запись (может быть битой) или undefined. */
  get(): Promise<unknown>;
  put(value: StoredDraft): Promise<void>;
  clear(): Promise<void>;
  /** После seal() put не пишет (resolve без записи); get и clear работают. */
  seal?(): void;
}

/**
 * Что раньше: результат (или ошибка) p либо fallback через ms.
 * Таймер снимается, когда p завершилось. Ошибка p после таймаута глотается.
 */
export function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      resolve(fallback);
    }, ms);
    p.then(
      (value) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(value);
      },
      (err: unknown) => {
        if (done) return; // пришла после таймаута — глотаем
        done = true;
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

/**
 * Очередь операций: каждая держит очередь до своего завершения или timeoutMs от своего
 * старта — что раньше. Вызывающий получает результат run как есть. Общая для черновика
 * онбординга и черновика поддержки (у каждого хранилища своя очередь).
 */
function createOpQueue(timeoutMs: number) {
  let tail: Promise<void> = Promise.resolve();

  return function enqueue<T>(run: () => Promise<T>): Promise<T> {
    let release!: () => void;
    const turn = new Promise<void>((resolve) => {
      release = resolve;
    });
    const prev = tail;
    tail = turn;
    return prev.then(() => {
      let op: Promise<T>;
      try {
        op = run();
      } catch (err) {
        op = Promise.reject(err);
      }
      const timer = setTimeout(release, timeoutMs);
      const settle = () => {
        clearTimeout(timer);
        release();
      };
      op.then(settle, settle);
      return op;
    });
  };
}

/**
 * Одна очередь для get / put / clear поверх inner. Операция держит очередь до своего
 * завершения или timeoutMs от своего старта — что раньше. Вызывающий получает результат
 * inner как есть. sealed проверяется в момент выполнения put, а не постановки.
 */
export function createSerialDraftStore(inner: DraftStore, timeoutMs = DRAFT_IO_TIMEOUT_MS): DraftStore {
  const enqueue = createOpQueue(timeoutMs);
  let sealed = false;

  return {
    get: () => enqueue(() => inner.get()),
    put: (value) => enqueue(() => (sealed ? Promise.resolve() : inner.put(value))),
    clear: () => enqueue(() => inner.clear()),
    seal: () => {
      sealed = true;
    },
  };
}

function isLaterStep(value: unknown): value is LaterStep {
  return typeof value === 'string' && (LATER_STEPS as readonly string[]).includes(value);
}

/** Только шаг; всё лишнее отбрасывается. */
export function sanitizeDraft(d: Draft): Draft {
  return { step: isLaterStep(d.step) ? d.step : 'offer' };
}

/** Проверка записи из хранилища. Не по формату → null. */
export function parseStoredDraft(raw: unknown): StoredDraft | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (r.v !== DRAFT_VERSION) return null;
  if (typeof r.tgUserId !== 'number' || !Number.isSafeInteger(r.tgUserId) || r.tgUserId <= 0) return null;
  if (typeof r.savedAt !== 'number' || !Number.isFinite(r.savedAt)) return null;
  if (!isLaterStep(r.step)) return null;
  return {
    v: DRAFT_VERSION,
    tgUserId: r.tgUserId,
    savedAt: r.savedAt,
    step: r.step,
  };
}

async function readDraft(store: DraftStore, tgUserId: number | null, now: number): Promise<Draft | null> {
  const raw = await store.get();
  if (raw === undefined || raw === null) return null;
  const stored = parseStoredDraft(raw);
  if (
    stored === null ||
    tgUserId === null ||
    stored.tgUserId !== tgUserId ||
    stored.step === 'finished' ||
    now - stored.savedAt > DRAFT_TTL_MS ||
    stored.savedAt > now + DRAFT_FUTURE_SKEW_MS
  ) {
    await store.clear();
    return null;
  }
  return sanitizeDraft(stored);
}

/**
 * Открыть черновик: чужой / неизвестный пользователь, старше 24 ч, битый,
 * старая метка finished → очистка и null. Хранилище не ответило за timeoutMs → null
 * (D-23); ошибка до таймаута — reject, как раньше.
 */
export function openDraft(
  store: DraftStore,
  tgUserId: number | null,
  now: number,
  timeoutMs = DRAFT_IO_TIMEOUT_MS,
): Promise<Draft | null> {
  return withTimeout<Draft | null>(readDraft(store, tgUserId, now), timeoutMs, null);
}

/**
 * Сохранить черновик. Шаг finished → очистка вместо записи (черновик не остаётся
 * на устройстве). Пользователь неизвестен → ничего не пишем. Порядок записей даёт очередь
 * хранилища (createSerialDraftStore).
 */
export async function saveDraft(store: DraftStore, tgUserId: number | null, draft: Draft, now: number): Promise<void> {
  const clean = sanitizeDraft(draft);
  if (clean.step === 'finished') {
    await store.clear();
    return;
  }
  if (tgUserId === null) return;
  await store.put({ v: DRAFT_VERSION, tgUserId, savedAt: now, ...clean });
}

/**
 * «Перейти к курсу»: seal (put после этого не пишет), затем черновик удаляется всегда
 * (и при известном, и при неизвестном пользователе) — метки finished на устройстве нет.
 * Ошибка хранилища (reject или синхронный throw) глотается без лога; onFinish вызывается
 * ровно 1 раз — после очистки или по таймауту timeoutMs (D-23).
 * Ошибка внутри самого onFinish не перехватывается.
 * tgUserId и now не используются (подпись прежняя — вызов в LaterSteps.tsx не меняется).
 */
export async function finishDraft(
  store: DraftStore,
  _tgUserId: number | null,
  _now: number,
  onFinish: () => void,
  timeoutMs = DRAFT_IO_TIMEOUT_MS,
): Promise<void> {
  store.seal?.();
  let clearing: Promise<void>;
  try {
    clearing = store.clear();
  } catch {
    // Хранилище недоступно — переход к курсу не блокируем, в лог ничего (ПДн).
    clearing = Promise.resolve();
  }
  try {
    await withTimeout<void>(clearing, timeoutMs, undefined);
  } catch {
    // Хранилище недоступно — переход к курсу не блокируем, в лог ничего (ПДн).
  }
  onFinish();
}

// ---- Хранилище в памяти (тесты; запасной вариант, если IndexedDB нет) ----

export interface MemoryDraftStore extends DraftStore {
  /** Что лежит в хранилище сейчас (для тестов). */
  peek(): unknown;
}

export function createMemoryDraftStore(): MemoryDraftStore {
  let value: unknown = undefined;
  return {
    get: async () => value,
    put: async (next) => {
      value = { ...next };
    },
    clear: async () => {
      value = undefined;
    },
    peek: () => value,
  };
}

// ---- Нативный IndexedDB ----

const DB_NAME = 'course-bot';
const DB_VERSION = 1;
const STORE_NAME = 'drafts';
const DRAFT_KEY = 'onboarding';

function openDb(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = factory.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE_NAME)) req.result.createObjectStore(STORE_NAME);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB: open failed'));
    req.onblocked = () => reject(new Error('IndexedDB: open blocked'));
  });
}

function withStore<T>(
  factory: IDBFactory,
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDb(factory).then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        let tx: IDBTransaction;
        let req: IDBRequest<T>;
        try {
          tx = db.transaction(STORE_NAME, mode);
          req = action(tx.objectStore(STORE_NAME));
        } catch (err) {
          db.close();
          reject(err);
          return;
        }
        tx.oncomplete = () => {
          db.close();
          resolve(req.result);
        };
        tx.onerror = () => {
          db.close();
          reject(tx.error ?? req.error ?? new Error('IndexedDB: transaction failed'));
        };
        tx.onabort = () => {
          db.close();
          reject(tx.error ?? new Error('IndexedDB: transaction aborted'));
        };
      }),
  );
}

export function createIndexedDbDraftStore(factory: IDBFactory): DraftStore {
  return {
    get: () => withStore<unknown>(factory, 'readonly', (s) => s.get(DRAFT_KEY)),
    put: (value) => withStore(factory, 'readwrite', (s) => s.put(value, DRAFT_KEY)).then(() => undefined),
    clear: () => withStore(factory, 'readwrite', (s) => s.delete(DRAFT_KEY)).then(() => undefined),
  };
}

/**
 * IndexedDB, если он есть; иначе — в памяти (черновик живёт до закрытия приложения).
 * Сверху — одна очередь с seal (D-23).
 */
export function createDraftStore(): DraftStore {
  const inner = typeof indexedDB === 'undefined' ? createMemoryDraftStore() : createIndexedDbDraftStore(indexedDB);
  return createSerialDraftStore(inner);
}

// ---- Черновик поддержки (miniapp-sup-1, Р-19): тема и текст вопроса ----

export const SUPPORT_TOPIC_CODES: readonly SupportTopicCode[] = ['s1', 's2', 's3', 's4', 's5', 's6', 's7', 'other'];

export interface SupportDraft {
  topic: SupportTopicCode | null;
  text: string;
}

export const EMPTY_SUPPORT_DRAFT: SupportDraft = { topic: null, text: '' };

export const SUPPORT_DRAFT_VERSION = 1;
/** Предел текста в черновике, кодовых точек (защита хранилища; сервер принимает до 2000). */
export const SUPPORT_DRAFT_MAX_CHARS = 4000;

export interface StoredSupportDraft extends SupportDraft {
  v: typeof SUPPORT_DRAFT_VERSION;
  tgUserId: number;
  savedAt: number;
}

export interface SupportDraftStore {
  /** Сырая запись (может быть битой) или undefined. */
  get(): Promise<unknown>;
  put(value: StoredSupportDraft): Promise<void>;
  clear(): Promise<void>;
}

const SUPPORT_DRAFT_KEY = 'support';

function emptySupportDraft(): SupportDraft {
  return { topic: EMPTY_SUPPORT_DRAFT.topic, text: EMPTY_SUPPORT_DRAFT.text };
}

function isSupportTopic(value: unknown): value is SupportTopicCode {
  return typeof value === 'string' && (SUPPORT_TOPIC_CODES as readonly string[]).includes(value);
}

function codePointCount(s: string): number {
  return Array.from(s).length;
}

function truncateCodePoints(s: string, max: number): string {
  const points = Array.from(s);
  return points.length > max ? points.slice(0, max).join('') : s;
}

/**
 * Проверка записи черновика поддержки. null — не объект; v не 1; tgUserId не равен
 * (или пользователь неизвестен); savedAt не число, дальше DRAFT_FUTURE_SKEW_MS в будущем
 * или старше DRAFT_TTL_MS; тема не из списка и не null; текст не строка или длиннее
 * SUPPORT_DRAFT_MAX_CHARS. Лишние поля отбрасываются.
 */
export function parseStoredSupportDraft(raw: unknown, tgUserId: number | null, now: number): SupportDraft | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (r.v !== SUPPORT_DRAFT_VERSION) return null;
  if (tgUserId === null || r.tgUserId !== tgUserId) return null;
  const savedAt = r.savedAt;
  if (typeof savedAt !== 'number' || !Number.isFinite(savedAt)) return null;
  if (savedAt > now + DRAFT_FUTURE_SKEW_MS) return null;
  if (now - savedAt > DRAFT_TTL_MS) return null;
  let topic: SupportTopicCode | null;
  if (r.topic === null) topic = null;
  else if (isSupportTopic(r.topic)) topic = r.topic;
  else return null;
  const text = r.text;
  if (typeof text !== 'string' || codePointCount(text) > SUPPORT_DRAFT_MAX_CHARS) return null;
  return { topic, text };
}

export interface MemorySupportDraftStore extends SupportDraftStore {
  /** Что лежит в хранилище сейчас (для тестов). */
  peek(): unknown;
}

export function createMemorySupportDraftStore(): MemorySupportDraftStore {
  let value: unknown = undefined;
  return {
    get: async () => value,
    put: async (next) => {
      value = { ...next };
    },
    clear: async () => {
      value = undefined;
    },
    peek: () => value,
  };
}

function createIndexedDbSupportDraftStore(factory: IDBFactory): SupportDraftStore {
  return {
    get: () => withStore<unknown>(factory, 'readonly', (s) => s.get(SUPPORT_DRAFT_KEY)),
    put: (value) => withStore(factory, 'readwrite', (s) => s.put(value, SUPPORT_DRAFT_KEY)).then(() => undefined),
    clear: () => withStore(factory, 'readwrite', (s) => s.delete(SUPPORT_DRAFT_KEY)).then(() => undefined),
  };
}

function createSerialSupportDraftStore(inner: SupportDraftStore, timeoutMs = DRAFT_IO_TIMEOUT_MS): SupportDraftStore {
  const enqueue = createOpQueue(timeoutMs);
  return {
    get: () => enqueue(() => inner.get()),
    put: (value) => enqueue(() => inner.put(value)),
    clear: () => enqueue(() => inner.clear()),
  };
}

/**
 * Черновик поддержки: IndexedDB по ключу support, если он есть; иначе — в памяти.
 * Сверху — своя очередь с таймаутом DRAFT_IO_TIMEOUT_MS, без seal.
 */
export function createSupportDraftStore(): SupportDraftStore {
  const inner =
    typeof indexedDB === 'undefined' ? createMemorySupportDraftStore() : createIndexedDbSupportDraftStore(indexedDB);
  return createSerialSupportDraftStore(inner);
}

async function readSupportDraft(store: SupportDraftStore, tgUserId: number | null, now: number): Promise<SupportDraft> {
  const raw = await store.get();
  if (raw === undefined || raw === null) return emptySupportDraft();
  const found = parseStoredSupportDraft(raw, tgUserId, now);
  if (found === null) {
    await store.clear();
    return emptySupportDraft();
  }
  return found;
}

/**
 * Открыть черновик поддержки: неизвестный или чужой пользователь, битая или старая запись →
 * очистка и пустой черновик. Ошибка хранилища или таймаут timeoutMs → пустой черновик.
 * Никогда не бросает.
 */
export async function openSupportDraft(
  store: SupportDraftStore,
  tgUserId: number | null,
  now: number,
  timeoutMs = DRAFT_IO_TIMEOUT_MS,
): Promise<SupportDraft> {
  try {
    const reading = Promise.resolve().then(() => readSupportDraft(store, tgUserId, now));
    return await withTimeout<SupportDraft>(reading, timeoutMs, emptySupportDraft());
  } catch {
    // Хранилище недоступно — экран работает с пустым черновиком, в лог ничего.
    return emptySupportDraft();
  }
}

/**
 * Сохранить черновик поддержки. Пользователь неизвестен или черновик пустой (темы нет и текст
 * из пробелов) → очистка; иначе запись с текстом не длиннее SUPPORT_DRAFT_MAX_CHARS.
 * Ошибки глотает, в лог не пишет.
 */
export async function saveSupportDraft(
  store: SupportDraftStore,
  tgUserId: number | null,
  draft: SupportDraft,
  now: number,
): Promise<void> {
  try {
    const topic = isSupportTopic(draft.topic) ? draft.topic : null;
    const text = typeof draft.text === 'string' ? draft.text : '';
    if (tgUserId === null || (topic === null && text.trim() === '')) {
      await store.clear();
      return;
    }
    await store.put({
      v: SUPPORT_DRAFT_VERSION,
      tgUserId,
      savedAt: now,
      topic,
      text: truncateCodePoints(text, SUPPORT_DRAFT_MAX_CHARS),
    });
  } catch {
    // Ошибка записи не мешает экрану, в лог ничего.
  }
}

/** Стереть черновик поддержки (после 201). Ошибки глотает. */
export async function clearSupportDraft(store: SupportDraftStore): Promise<void> {
  try {
    await store.clear();
  } catch {
    // Хранилище недоступно — в лог ничего.
  }
}
