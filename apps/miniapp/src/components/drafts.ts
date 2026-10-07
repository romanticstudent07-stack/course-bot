// apps/miniapp/src/components/drafts.ts — черновик анкеты после pid (1e-2, 1e-2b-2, returning-2).
//
// Нативный IndexedDB без библиотек, за интерфейсом DraftStore (в тестах — хранилище в памяти).
// Это ЕДИНСТВЕННЫЙ файл Mini App, который пишет на устройство.
//
// Правила (I4 §7 R380_cleanup, карточки 1e-2 §7, 1e-2b-2 §7, returning-2 §7.4):
//   - в черновике только step, email, city + служебные v, tgUserId, savedAt;
//     дату рождения сюда не класть НИКОГДА (её и нет в типе Draft; sanitizeDraft
//     отбрасывает любые лишние поля). short_no, status и reasons сервера — тоже нет;
//   - черновик привязан к tg_user_id: другой tg_user_id или неизвестный → полная
//     очистка сразу при открытии;
//   - черновик старше 24 ч (от последнего сохранения) → удалить при открытии;
//   - битая запись → удалить;
//   - метки finished на устройстве НЕТ (returning-2): «пройден ли онбординг» решает сервер
//     (GET /onboarding/status). Шаг 'finished' — это экран, а не хранимая метка:
//     saveDraft со step 'finished' → очистка; openDraft нашёл старую запись 'finished' →
//     очистка и null; «Перейти к курсу» (finishDraft) → очистка. Ошибка хранилища переход
//     не блокирует и в лог не пишется.
// На сервер черновик не уходит: эндпоинта анкеты нет.

export const LATER_STEPS = ['offer', 'email', 'city', 'checkup', 'rules', 'finished'] as const;
export type LaterStep = (typeof LATER_STEPS)[number];

/** Кнопки-города (заглушка до решения по списку). */
export const CITY_OPTIONS = ['Москва', 'Санкт-Петербург', 'Другой город'] as const;

export interface Draft {
  step: LaterStep;
  email: string;
  city: string;
}

export const EMPTY_DRAFT: Draft = { step: 'offer', email: '', city: '' };

export const DRAFT_VERSION = 1;
export const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;
/** savedAt дальше этого в будущем — запись считается битой. */
export const DRAFT_FUTURE_SKEW_MS = 60 * 1000;
export const EMAIL_MAX_LENGTH = 254;

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
}

function isLaterStep(value: unknown): value is LaterStep {
  return typeof value === 'string' && (LATER_STEPS as readonly string[]).includes(value);
}

function isCity(value: unknown): value is string {
  return value === '' || (typeof value === 'string' && (CITY_OPTIONS as readonly string[]).includes(value));
}

/** Только три поля черновика; всё лишнее отбрасывается. */
export function sanitizeDraft(d: Draft): Draft {
  return {
    step: isLaterStep(d.step) ? d.step : 'offer',
    email: typeof d.email === 'string' ? d.email.slice(0, EMAIL_MAX_LENGTH) : '',
    city: isCity(d.city) ? d.city : '',
  };
}

/** Проверка записи из хранилища. Не по формату → null. */
export function parseStoredDraft(raw: unknown): StoredDraft | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (r.v !== DRAFT_VERSION) return null;
  if (typeof r.tgUserId !== 'number' || !Number.isSafeInteger(r.tgUserId) || r.tgUserId <= 0) return null;
  if (typeof r.savedAt !== 'number' || !Number.isFinite(r.savedAt)) return null;
  if (!isLaterStep(r.step)) return null;
  if (typeof r.email !== 'string' || r.email.length > EMAIL_MAX_LENGTH) return null;
  if (!isCity(r.city)) return null;
  return {
    v: DRAFT_VERSION,
    tgUserId: r.tgUserId,
    savedAt: r.savedAt,
    step: r.step,
    email: r.email,
    city: r.city,
  };
}

/**
 * Открыть черновик: чужой / неизвестный пользователь, старше 24 ч, битый,
 * старая метка finished → очистка и null.
 */
export async function openDraft(store: DraftStore, tgUserId: number | null, now: number): Promise<Draft | null> {
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
 * Сохранить черновик. Шаг finished → очистка вместо записи (email и город не остаются
 * на устройстве). Пользователь неизвестен → ничего не пишем.
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
 * «Перейти к курсу»: черновик удаляется всегда (и при известном, и при неизвестном
 * пользователе) — метки finished на устройстве нет. Ошибка хранилища (reject или синхронный
 * throw) глотается без лога; onFinish вызывается ровно 1 раз — после попытки очистки.
 * Ошибка внутри самого onFinish не перехватывается.
 * tgUserId и now не используются (подпись прежняя — вызов в LaterSteps.tsx не меняется).
 */
export async function finishDraft(
  store: DraftStore,
  _tgUserId: number | null,
  _now: number,
  onFinish: () => void,
): Promise<void> {
  try {
    await store.clear();
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

/** IndexedDB, если он есть; иначе — в памяти (черновик живёт до закрытия приложения). */
export function createDraftStore(): DraftStore {
  if (typeof indexedDB === 'undefined') return createMemoryDraftStore();
  return createIndexedDbDraftStore(indexedDB);
}
