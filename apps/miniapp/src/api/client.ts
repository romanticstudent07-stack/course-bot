// apps/miniapp/src/api/client.ts — HTTP-клиент к backend (/miniapp/v1/**).
//
// Правила (AGENTS.md, miniapp-api-contract.yaml):
//   - на сервер уходит СЫРАЯ строка initData в заголовке X-Telegram-Init-Data;
//     initDataUnsafe для решений не используется;
//   - базовый URL — из VITE_API_BASE_URL (пусто = тот же origin, CSP E2 connect-src 'self');
//   - state-меняющие вызовы несут X-Client-Op-Id (uuid v4) — идемпотентность (D-17);
//   - ответ 429: заголовок Retry-After → ApiError.retryAfter (parseRetryAfter, miniapp-sup-1).
import { retrieveRawInitData } from '@telegram-apps/sdk-react';

export const INIT_DATA_HEADER = 'X-Telegram-Init-Data';
export const CLIENT_OP_ID_HEADER = 'X-Client-Op-Id';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    /** Секунды из Retry-After (только для 429, только целое > 0); иначе null. */
    public readonly retryAfter: number | null = null,
    /** payload.details ошибки, только если это объект (не массив, не null); иначе undefined. */
    public readonly details: Record<string, unknown> | undefined = undefined,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Нормализует базовый URL: без завершающего слэша; пусто — относительные пути. */
export function normalizeBaseUrl(raw: string | undefined): string {
  return (raw ?? '').trim().replace(/\/+$/, '');
}

export function buildUrl(baseUrl: string, path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizeBaseUrl(baseUrl)}${cleanPath}`;
}

/**
 * Retry-After в секундах: только строка из цифр, целое > 0 и safe integer; иначе null
 * (дата HTTP, дробь, ноль, пусто — null).
 */
export function parseRetryAfter(v: string | null): number | null {
  if (v === null || !/^\d+$/.test(v)) return null;
  const n = Number(v);
  return Number.isSafeInteger(n) && n > 0 ? n : null;
}

function readInitData(): string | undefined {
  try {
    return retrieveRawInitData();
  } catch {
    return undefined;
  }
}

/**
 * tg_user_id из сырой строки initData — ТОЛЬКО для привязки локального черновика
 * к пользователю (drafts.ts: другой пользователь → полная очистка). Для решений
 * сервера не используется: сервер берёт tg_user_id из проверенной initData.
 */
export function tgUserIdFromInitData(raw: string | undefined): number | null {
  if (!raw) return null;
  try {
    const userRaw = new URLSearchParams(raw).get('user');
    if (!userRaw) return null;
    const user: unknown = JSON.parse(userRaw);
    if (typeof user !== 'object' || user === null) return null;
    const id = (user as { id?: unknown }).id;
    return typeof id === 'number' && Number.isSafeInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function readTgUserId(): number | null {
  return tgUserIdFromInitData(readInitData());
}

/** uuid v4 для X-Client-Op-Id (getRandomValues есть во всех webview, randomUUID — не везде). */
export function newClientOpId(): string {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT';
  body?: unknown;
  clientOpId?: string;
  /** Отмена запроса (координатор чтений pause.ts); передаётся в fetch как есть. */
  signal?: AbortSignal;
}

/** details из тела ошибки: только объект — не массив и не null. */
function pickDetails(payload: unknown): Record<string, unknown> | undefined {
  if (typeof payload !== 'object' || payload === null) return undefined;
  const d = (payload as { details?: unknown }).details;
  return typeof d === 'object' && d !== null && !Array.isArray(d) ? (d as Record<string, unknown>) : undefined;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const initData = readInitData();
  if (initData) headers[INIT_DATA_HEADER] = initData;
  if (options.clientOpId) headers[CLIENT_OP_ID_HEADER] = options.clientOpId;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(buildUrl(import.meta.env.VITE_API_BASE_URL ?? '', path), {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: 'same-origin',
    signal: options.signal,
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const err = (payload ?? {}) as { code?: string; message?: string };
    const retryAfter = response.status === 429 ? parseRetryAfter(response.headers.get('Retry-After')) : null;
    throw new ApiError(
      response.status,
      err.code ?? 'HTTP_ERROR',
      err.message ?? response.statusText,
      retryAfter,
      pickDetails(payload),
    );
  }
  return payload as T;
}

// ---- Онбординг (SEAM-1) — контракт build/miniapp-api-contract.yaml ----
// UI: apps/miniapp/src/components/OnboardingFlow.tsx (до pid) и LaterSteps.tsx (после pid);
// старт Mini App — App.tsx + startup.ts (getOnboardingStatus, returning-2).

/** Единый реестр согласий C0–C6 (Consent.id в контракте). До pid обязательны C0 и C1. */
export type ConsentId = 'C0' | 'C1' | 'C2' | 'C3' | 'C4' | 'C5' | 'C6';

export interface FirstLaunchRequest {
  /** Дата рождения, ISO-8601 (YYYY-MM-DD). Возрастной гейт — на сервере (ADD3). */
  birth_date: string;
  /** Только id согласий; текст и его версию выбирает сервер (B-2, D-10). */
  consents: ConsentId[];
}

export interface PidCreated {
  pid: string;
  short_no: string;
}

/**
 * clientOpId — один на весь онбординг; повтор после ошибки уходит с тем же id (D-17).
 * 403 ACCESS_NOT_GRANTED — доступ не выдан (Р-2).
 */
export const postFirstLaunch = (body: FirstLaunchRequest, clientOpId: string) =>
  apiRequest<PidCreated>('/miniapp/v1/onboarding/first-launch', { method: 'POST', body, clientOpId });

/**
 * Статус онбординга (returning-1). Решение «показывать ли экраны 18+ и согласий» принимает
 * сервер; клиент версии и тексты согласий не сравнивает и ответ на устройстве не хранит.
 */
export type OnboardingStatus =
  | { status: 'returning'; short_no: string }
  | { status: 'reconsent'; reasons: string[] }
  | { status: 'new' }
  | { status: 'no_access' };

/**
 * Только чтение: без X-Client-Op-Id (запрос ничего не меняет). Ошибки — 401, 429, 503.
 * 200 no_access (Р-2).
 */
export const getOnboardingStatus = () => apiRequest<OnboardingStatus>('/miniapp/v1/onboarding/status');

// ---- Согласия (1e-2): только чтение своих ----

export interface ConsentOut {
  id: ConsentId;
  given_at: string;
  revoked_at: string | null;
  legal_status: string;
}

export const getConsents = () => apiRequest<ConsentOut[]>('/miniapp/v1/consents');

// ---- Тексты (text_registry, 1d) ----

export interface TextOut {
  key: string;
  tone: string;
  legal_status: string;
  text: string;
  plurals_ru?: Record<string, string> | null;
}

export interface TextsBulkResponse {
  texts: TextOut[];
  /** Ключи, которых нет в реестре; клиент показывает нейтральную заглушку. */
  missing: string[];
}

export const postTextsBulk = (keys: string[]) =>
  apiRequest<TextsBulkResponse>('/miniapp/v1/texts/bulk', { method: 'POST', body: { keys } });

// ---- День (day-screen-a): GET /day/current, POST /day/test-enter ----
// «Какой экран» решает только status, «можно ли нажать» — только buttons_active.
// Окно 04:00–00:00 клиент не считает; время — ISO 8601 со сдвигом пояса участника.

export type DayStatus = 'not_started' | 'entering' | 'open' | 'submitted' | 'queued' | 'closed';

export interface DayBlock {
  block_id: string;
  title_key: string;
  help_key: string;
  critical: boolean;
  mark: 'done' | 'not_done' | null;
}

export interface DayPosition {
  stage_no: number;
  module_no: number;
  day_no: number;
}

/** not_started / entering — только status, lives, test_entry; остальные поля могут отсутствовать. */
export interface DayCurrent {
  status: DayStatus;
  lives: number;
  test_entry: boolean;
  position?: DayPosition | null;
  day_started_at?: string | null;
  blocks?: DayBlock[] | null;
  min_optional?: number | null;
  can_submit?: boolean | null;
  active_from?: string | null;
  deadline_at?: string | null;
  queued_until?: string | null;
  buttons_active?: boolean | null;
  /**
   * День рефлексии (03 §3.12, miniapp-refl-1). Д1: сервер отдаёт поле только в open, submitted
   * и closed; в queued и без позиции его нет — поэтому необязательное. Клиент день не считает.
   */
  reflection_required?: boolean | null;
}

/** Только чтение. Ошибки: 401, 404 PARTICIPANT_NOT_FOUND, 429, 503. */
export const getDayCurrent = () => apiRequest<DayCurrent>('/miniapp/v1/day/current');

/** Тестовый вход (флаг DAY_TEST_ENTRY_ENABLED): тела нет, X-Client-Op-Id не нужен. */
export const postDayTestEnter = () =>
  apiRequest<{ status: 'already' | 'entering' }>('/miniapp/v1/day/test-enter', { method: 'POST' });

// ---- День (day-screen-b): PUT /day/marks, POST /day/report/submit ----
// Каждая отметка сразу уходит на сервер (DM 3.4); на устройстве не хранится.

export type DayMarkValue = 'done' | 'not_done';

export interface DayMarkIn {
  block_id: string;
  value: DayMarkValue;
}

export type DayMarkOut = DayMarkIn;

export interface DayReportIn {
  /** Каждый блок дня ровно один раз, в порядке блоков. */
  marks: DayMarkIn[];
  /** Рефлексия — только в день рефлексии; текст как введён: strip и обрезку длины делает сервер. */
  reflection?: string;
}

export interface DayReportOut {
  verdict: 'passed' | 'not_passed' | 'all_not_done';
  queued: true;
}

/**
 * UPSERT отметки: X-Client-Op-Id не нужен (повтор безопасен).
 * Ошибки: 404 PARTICIPANT_NOT_FOUND; 409 DAY_NOT_STARTED / DAY_NOT_ACTIVE / DAY_CLOSED /
 * DAY_ALREADY_SUBMITTED; 422 BLOCK_NOT_IN_DAY; 401, 429, 503.
 */
export const putDayMark = (body: DayMarkIn) =>
  apiRequest<DayMarkOut>('/miniapp/v1/day/marks', { method: 'PUT', body });

/**
 * Отчёт дня. clientOpId — один на попытку с тем же телом: повтор после ошибки — с ним же (D-17).
 * 200 — только после commit. Вердикт экран не показывает (DM 3.19).
 * 422 REFLECTION_REQUIRED — день рефлексии без текста (меньше 2 символов после strip).
 */
export const postDayReport = (body: DayReportIn, clientOpId: string) =>
  apiRequest<DayReportOut>('/miniapp/v1/day/report/submit', { method: 'POST', body, clientOpId });

// ---- Анкета онбординга (api-i3-2; карточка miniapp-i3-1a §7.1) ----
// Значения анкеты на устройстве не хранятся и в лог не пишутся (Р-16): только тело POST.

export type FormGender = 'male' | 'female';

export interface FormWellbeingOption {
  code: string;
  text: string;
}

export interface FormTimezone {
  tz: string;
  city: string;
}

/** [город, регион, i] — i: индекс в timezones. */
export type FormCity = [string, string, number];

export interface FormConfig {
  version: number;
  genders: FormGender[];
  wellbeing_question: string;
  wellbeing: FormWellbeingOption[];
  weight: { min: number; max: number; step: number };
  /** 11 поясов РФ — кнопки «Моего города нет» (Р-17). */
  timezones: FormTimezone[];
  fallback_title: string;
  cities: FormCity[];
}

export interface FormStatus {
  submitted: boolean;
  created_at: string | null;
}

/** Тело POST ровно из 4 ключей; города нет (Р-16). */
export interface FormBody {
  tz: string;
  gender: FormGender;
  wellbeing_code: string;
  weight_kg: number;
}

export interface FormCreated {
  created_at: string;
}

/** Только чтение. Ошибки: 401, 429, 503. */
export const getFormConfig = () => apiRequest<FormConfig>('/miniapp/v1/onboarding/form/config');

/** Только чтение, без X-Client-Op-Id. Ошибки: 401, 404 PARTICIPANT_NOT_FOUND, 429, 503. */
export const getForm = () => apiRequest<FormStatus>('/miniapp/v1/onboarding/form');

/**
 * Отправка анкеты. clientOpId — один на попытку с тем же телом: повтор после ошибки — с ним же (D-17).
 * Ошибки: 404; 409 RECONSENT_REQUIRED / ONBOARDING_FORM_EXISTS / IDEMPOTENCY_CONFLICT;
 * 422 VALIDATION_ERROR; 401, 429, 503.
 */
export const postForm = (body: FormBody, clientOpId: string) =>
  apiRequest<FormCreated>('/miniapp/v1/onboarding/form', { method: 'POST', body, clientOpId });

// ---- Чек-Ап онбординга (api-i3-4; карточка miniapp-i3-1b §7.1) ----
// Ответы и зона на устройстве не хранятся и в лог не пишутся (Р-18, 2А): только тело POST и state React.

export interface CheckupBlock {
  id: number;
  title: string;
}

export interface CheckupQuestion {
  id: string;
  block: number;
  text: string;
}

export interface CheckupZone {
  id: string;
  title: string;
  text: string;
}

export interface CheckupConfig {
  version: string;
  scale: { min: number; max: number };
  blocks: CheckupBlock[];
  questions: CheckupQuestion[];
  zones: CheckupZone[];
  disclaimer: string;
}

export interface CheckupStatus {
  completed: boolean;
  created_at: string | null;
}

/** Тело POST: Чек-Ап онбординга, 15 целых 0–3. */
export interface CheckupSubmitBody {
  occasion: 'onboarding';
  answers: number[];
}

export interface CheckupSubmitResult {
  zone: string;
  config_version: string;
  created_at: string;
}

/** Только чтение. Ошибки: 401, 429, 503. */
export const getCheckupConfig = () => apiRequest<CheckupConfig>('/miniapp/v1/checkup/config');

/** Только чтение, без X-Client-Op-Id. Ошибки: 401, 404 PARTICIPANT_NOT_FOUND, 429, 503. */
export const getCheckupStatus = () => apiRequest<CheckupStatus>('/miniapp/v1/checkup/status');

/**
 * Отправка Чек-Апа. clientOpId — один на попытку с тем же телом: повтор после ошибки — с ним же (D-17).
 * Ошибки: 404 PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED / IDEMPOTENCY_CONFLICT / CHECKUP_EXISTS;
 * 422; 401, 429, 503.
 */
export const postCheckupSubmit = (body: CheckupSubmitBody, clientOpId: string) =>
  apiRequest<CheckupSubmitResult>('/miniapp/v1/checkup/submit', { method: 'POST', body, clientOpId });

// ---- Карточка участника (api-i3-3; карточка miniapp-i3-2a §7.1) ----
// Ответ живёт только в state React: не на устройство, не в лог, не в адрес. Балла Чек-Апа нет.

export type ZoneId = 'green' | 'yellow' | 'red';

export interface MeMeasurements {
  weight_start_kg: number | null;
  weight_current_kg: number | null;
  checkup_completed: boolean;
  zone_start: ZoneId | null;
  zone_last: ZoneId | null;
}

export interface MeCard {
  /** Вид «#000123». */
  short_no: string;
  /** date-time, UTC. */
  registered_at: string;
  /** IANA-пояс участника или null. */
  tz: string | null;
  position: DayPosition | null;
  lives: number;
  measurements: MeMeasurements;
}

/** Только чтение, без X-Client-Op-Id. Ошибки: 401, 404 PARTICIPANT_NOT_FOUND, 429, 503 SERVICE_UNAVAILABLE. */
export const getMeCard = () => apiRequest<MeCard>('/miniapp/v1/me/card');

// ---- Карта изменений (api-i3-3; карточка miniapp-i3-2b §7.1) ----
// Ответ живёт только в state React: не на устройство, не в лог, не в адрес.
// Слои по порядку: anthro, wellbeing, checkup, functional; фото нет (Р-3); балла Чек-Апа нет.

export interface ChangeMapPoint {
  /** anthro — число (кг); wellbeing — код (на экран не выводится); checkup — зона. */
  value: number | string;
  /** date-time, UTC. */
  at: string;
}

export interface ChangeMapLayer {
  layer: string;
  metric: string | null;
  baseline: ChangeMapPoint | null;
  /** До 5 последних точек после baseline, по возрастанию. */
  recent: ChangeMapPoint[];
}

export interface MeChangeMap {
  layers: ChangeMapLayer[];
}

/** Только чтение, без X-Client-Op-Id. Ошибки: 401, 404 PARTICIPANT_NOT_FOUND, 429, 503 SERVICE_UNAVAILABLE. */
export const getMeChangeMap = () => apiRequest<MeChangeMap>('/miniapp/v1/me/change-map');

// ---- Поддержка (api-sup-1; карточка miniapp-sup-1 §7.1, Р-19) ----
// Текст вопроса — только тело POST: не в лог, не в адрес, не в query.
// Сервер: len(text.strip()) >= 2 и len(text) <= 2000 по сырому тексту; NUL → 422.

export type SupportTopicCode = 's1' | 's2' | 's3' | 's4' | 's5' | 's6' | 's7' | 'other';

export interface SupportQuestionBody {
  topic_code: SupportTopicCode;
  text: string;
}

/**
 * Вопрос в поддержку. clientOpId — один на попытку: повтор той же попытки — с ним же → 201 без
 * нового поста. 201 {"status":"sent"}. Ошибки: 401; 404 PARTICIPANT_NOT_FOUND; 409 RECONSENT_REQUIRED;
 * 422 VALIDATION_ERROR / SUPPORT_TOPIC_INVALID / SUPPORT_TEXT_INVALID; 429 RATE_LIMITED /
 * SUPPORT_TOO_FREQUENT + Retry-After; 503 SERVICE_UNAVAILABLE / SERVICE_MISCONFIGURED.
 */
export const postSupportQuestion = (body: SupportQuestionBody, clientOpId: string) =>
  apiRequest<{ status: 'sent' }>('/miniapp/v1/support/question', { method: 'POST', body, clientOpId });

// ---- Паузы (api-pause-2; карточка miniapp-pause-c1 §7.1, Р-6а / R-2026-11-21) ----
// Типы — буква в букву по моделям apps/api/app/routers/pause.py (PauseOut, PauseStatusOut,
// PauseRequestOut, AcceptedOut). datetime — строка ISO 8601, date — строка YYYY-MM-DD.
// Три POST вызывает только отправитель очереди components/pauseSend.ts.

export interface PauseOut {
  id: number;
  status: string;
  start_at: string;
  planned_end_at: string;
}

export interface PauseStatus {
  budget_days_left: number;
  budget_days_total: number;
  cycle_ends_at: string | null;
  pause: PauseOut | null;
  can_request: boolean;
  /** "already_open" при открытой строке; иначе причина отказа или null. */
  refusal: string | null;
  /** Местная дата начала паузы YYYY-MM-DD; приходит всегда, и при can_request = false. */
  start_date: string;
}

export interface PauseRequestBody {
  /** 1..7. */
  days: number;
  /** start_date из последнего GET /pause, подтверждённая участником (R-2026-11-21). */
  start_date: string;
}

export interface PauseTargetBody {
  pause_id: number;
}

export interface PauseRequestOut {
  pause: PauseOut;
}

export interface PauseAcceptedOut {
  status: string;
}

/** Только чтение, без X-Client-Op-Id. Ошибки: 401, 404 PARTICIPANT_NOT_FOUND, 429, 503. */
export const getPause = (signal?: AbortSignal) =>
  apiRequest<PauseStatus>('/miniapp/v1/pause', { signal });

/**
 * Заявка на паузу → 201 {"pause": {...}}. clientOpId — из слота очереди, повтор — с ним же.
 * Ошибки: 404 PARTICIPANT_NOT_FOUND; 409 PAUSE_ALREADY_OPEN / PAUSE_REFUSED (details.reason, в т. ч.
 * start_date_passed) / IDEMPOTENCY_CONFLICT; 422 VALIDATION_ERROR; 401, 429 + Retry-After, 503.
 */
export const postPauseRequest = (body: PauseRequestBody, clientOpId: string) =>
  apiRequest<PauseRequestOut>('/miniapp/v1/pause/request', { method: 'POST', body, clientOpId });

/**
 * Отмена заявки до старта → 202 {"status":"accepted"}.
 * Ошибки: 404 PARTICIPANT_NOT_FOUND; 409 PAUSE_NOT_CANCELLABLE / IDEMPOTENCY_CONFLICT;
 * 422 VALIDATION_ERROR; 401, 429 + Retry-After, 503.
 */
export const postPauseCancel = (body: PauseTargetBody, clientOpId: string) =>
  apiRequest<PauseAcceptedOut>('/miniapp/v1/pause/cancel', { method: 'POST', body, clientOpId });

/**
 * Досрочный выход из активной паузы → 202 {"status":"accepted"}.
 * Ошибки: 404 PARTICIPANT_NOT_FOUND; 409 PAUSE_NOT_ACTIVE / IDEMPOTENCY_CONFLICT;
 * 422 VALIDATION_ERROR; 401, 429 + Retry-After, 503.
 */
export const postPauseResume = (body: PauseTargetBody, clientOpId: string) =>
  apiRequest<PauseAcceptedOut>('/miniapp/v1/pause/resume', { method: 'POST', body, clientOpId });
