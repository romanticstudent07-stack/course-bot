// apps/miniapp/src/components/pauseQueueStore.ts — хранилище очереди пауз (miniapp-pause-b1, T5-B1).
// Своя БД course-bot-pause-queue v1, хранилище slots; БД черновиков (drafts.ts) и её версию не трогаем.
// Один слот на владельца (ключ 'slot:' + ownerId), флаг 'wipe-pending' и ключ 'owner' в той же БД.
// claimOwner (miniapp-pause-c2): ключа 'owner' нет → записать, 'same'; равен → 'same'; другой → 'changed'
//   без перезаписи; ошибка хранилища → 'unavailable'. wipeAll стирает и ключ 'owner'.
// write → true только после завершения транзакции; ошибка или слот не по формату → false.
// В слоте только kind, неизменные аргументы, opId, владелец и расписание (R-2026-11-21):
//   без токенов, данных запуска Telegram, ответов сервера и снимка экрана.
// Слот битый, старше 24 ч или из будущего дальше 60 с — удалить при чтении (I4 R380).
// wipeAll — полная очистка: сначала БД course-bot, затем БД очереди (I4 R339 conflict_ux, R380).
//   Любая не удалилась (blocked или error) → 'blocked', sendClosed() = true до перезагрузки, флаг остаётся.
// Ошибки хранилища глотаются, в лог не пишутся. Нет IndexedDB → хранилище в памяти, как в drafts.ts.
// В main модуль ничего не вызывает (подключение — miniapp-pause-b2).

export type PauseOpKind = 'request' | 'cancel' | 'resume';
export type PauseOpArgs = { days: number; start_date: string } | { pause_id: number };
export type PausePhase = 'queued' | 'uncertain' | 'stopped';

export interface PauseSlot {
  ownerId: string;
  kind: PauseOpKind;
  args: PauseOpArgs;
  opId: string;
  phase: PausePhase;
  attempt: number;
  notBefore: number;
  /** мс, время первой записи; ставит enqueue (B2), повторы не меняют. */
  savedAt: number;
}

export interface PauseQueueStore {
  read(ownerId: string, now: number): Promise<PauseSlot | null>;
  write(slot: PauseSlot): Promise<boolean>;
  claimOwner(ownerId: string): Promise<'same' | 'changed' | 'unavailable'>;
  clear(ownerId: string): Promise<void>;
  setWipePending(): Promise<void>;
  isWipePending(): Promise<boolean>;
  wipeAll(): Promise<'done' | 'blocked'>;
  sendClosed(): boolean;
}

export const PAUSE_DB_NAME = 'course-bot-pause-queue';
export const PAUSE_DB_VERSION = 1;
export const DRAFTS_DB_NAME = 'course-bot';
export const PAUSE_SLOT_TTL_MS = 24 * 60 * 60 * 1000;
export const PAUSE_SLOT_FUTURE_SKEW_MS = 60 * 1000;
const STORE_NAME = 'slots';
const WIPE_KEY = 'wipe-pending';
const OWNER_KEY = 'owner';

const KINDS: readonly PauseOpKind[] = ['request', 'cancel', 'resume'];
const PHASES: readonly PausePhase[] = ['queued', 'uncertain', 'stopped'];

function slotKey(ownerId: string): string {
  return 'slot:' + ownerId;
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function parseArgs(kind: PauseOpKind, raw: unknown): PauseOpArgs | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const a = raw as Record<string, unknown>;
  if (kind === 'request') {
    if (typeof a.days === 'number' && Number.isSafeInteger(a.days) && typeof a.start_date === 'string') {
      return { days: a.days, start_date: a.start_date };
    }
    return null;
  }
  if (typeof a.pause_id === 'number' && Number.isSafeInteger(a.pause_id)) return { pause_id: a.pause_id };
  return null;
}

/** Проверка записи. Не по формату → null; лишние поля отбрасываются. */
export function parsePauseSlot(raw: unknown): PauseSlot | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.ownerId !== 'string' || r.ownerId === '') return null;
  if (typeof r.kind !== 'string' || !(KINDS as readonly string[]).includes(r.kind)) return null;
  const kind = r.kind as PauseOpKind;
  const args = parseArgs(kind, r.args);
  if (args === null) return null;
  if (typeof r.opId !== 'string' || r.opId === '') return null;
  if (typeof r.phase !== 'string' || !(PHASES as readonly string[]).includes(r.phase)) return null;
  if (!isNum(r.attempt) || !isNum(r.notBefore) || !isNum(r.savedAt)) return null;
  return {
    ownerId: r.ownerId,
    kind,
    args,
    opId: r.opId,
    phase: r.phase as PausePhase,
    attempt: r.attempt,
    notBefore: r.notBefore,
    savedAt: r.savedAt,
  };
}

interface Backend {
  get(key: string): Promise<unknown>;
  put(key: string, value: unknown): Promise<void>;
  del(key: string): Promise<void>;
  deleteDb(name: string): Promise<'done' | 'blocked'>;
}

function createMemoryBackend(): Backend {
  const data = new Map<string, string>();
  return {
    get: async (key) => {
      const v = data.get(key);
      return v === undefined ? undefined : (JSON.parse(v) as unknown);
    },
    put: async (key, value) => {
      data.set(key, JSON.stringify(value));
    },
    del: async (key) => {
      data.delete(key);
    },
    deleteDb: async (name) => {
      if (name === PAUSE_DB_NAME) data.clear();
      return 'done';
    },
  };
}

function openDb(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = factory.open(PAUSE_DB_NAME, PAUSE_DB_VERSION);
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
          reject(tx.error ?? new Error('IndexedDB: transaction failed'));
        };
        tx.onabort = () => {
          db.close();
          reject(tx.error ?? new Error('IndexedDB: transaction aborted'));
        };
      }),
  );
}

function createIdbBackend(factory: IDBFactory): Backend {
  return {
    get: (key) => withStore<unknown>(factory, 'readonly', (s) => s.get(key)),
    put: (key, value) => withStore(factory, 'readwrite', (s) => s.put(value, key)).then(() => undefined),
    del: (key) => withStore(factory, 'readwrite', (s) => s.delete(key)).then(() => undefined),
    deleteDb: (name) =>
      new Promise<'done' | 'blocked'>((resolve) => {
        let req: IDBOpenDBRequest;
        try {
          req = factory.deleteDatabase(name);
        } catch {
          resolve('blocked');
          return;
        }
        req.onsuccess = () => resolve('done');
        req.onerror = () => resolve('blocked');
        req.onblocked = () => resolve('blocked');
      }),
  };
}

async function safe<T>(run: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await run();
  } catch {
    // Хранилище недоступно — в лог ничего.
    return fallback;
  }
}

/** По умолчанию globalThis.indexedDB; null или его нет → хранилище в памяти. */
export function createPauseQueueStore(idb?: IDBFactory | null): PauseQueueStore {
  const factory = idb === undefined ? ((globalThis as { indexedDB?: IDBFactory }).indexedDB ?? null) : idb;
  const backend = factory ? createIdbBackend(factory) : createMemoryBackend();
  let closed = false;

  return {
    read: (ownerId, now) =>
      safe(async () => {
        const raw = await backend.get(slotKey(ownerId));
        if (raw === undefined || raw === null) return null;
        const slot = parsePauseSlot(raw);
        if (
          slot === null ||
          slot.ownerId !== ownerId ||
          now - slot.savedAt > PAUSE_SLOT_TTL_MS ||
          slot.savedAt > now + PAUSE_SLOT_FUTURE_SKEW_MS
        ) {
          await backend.del(slotKey(ownerId));
          return null;
        }
        return slot;
      }, null),
    write: (slot) =>
      safe(async () => {
        const clean = parsePauseSlot(slot);
        if (clean === null) return false;
        await backend.put(slotKey(clean.ownerId), clean);
        return true;
      }, false),
    claimOwner: (ownerId) =>
      safe(async () => {
        const cur = await backend.get(OWNER_KEY);
        if (cur === undefined || cur === null) {
          await backend.put(OWNER_KEY, ownerId);
          return 'same' as const;
        }
        return cur === ownerId ? ('same' as const) : ('changed' as const);
      }, 'unavailable' as const),
    clear: (ownerId) => safe(() => backend.del(slotKey(ownerId)), undefined),
    setWipePending: () => safe(() => backend.put(WIPE_KEY, true), undefined),
    isWipePending: () => safe(async () => (await backend.get(WIPE_KEY)) === true, false),
    wipeAll: async () => {
      const drafts = await safe(() => backend.deleteDb(DRAFTS_DB_NAME), 'blocked' as const);
      const queue = drafts === 'done' ? await safe(() => backend.deleteDb(PAUSE_DB_NAME), 'blocked' as const) : 'blocked';
      if (drafts === 'done' && queue === 'done') return 'done';
      closed = true;
      return 'blocked';
    },
    sendClosed: () => closed,
  };
}
