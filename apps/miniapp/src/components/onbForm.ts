// apps/miniapp/src/components/onbForm.ts — чистые функции экрана onb.form (miniapp-i3-1a).
//
// Без React и без запросов (тесты — vitest, environment node). Экран — OnbForm.tsx.
// Город → только tz (Р-16): город в тело POST не идёт; подсказки — с 2 символов, совпадение
// с начала названия, до 10, в порядке cities; засчитывается только выбор из подсказок или
// кнопка пояса из «Моего города нет» (Р-17, 3А).
// Значения анкеты живут только в state React: не на устройство, не в лог, не в URL (Р-16).
import { ApiError, type FormBody, type FormCity, type FormConfig, type FormGender } from '../api/client.ts';

export const SUGGEST_MIN_CHARS = 2;
export const SUGGEST_LIMIT = 10;

/** Нижний регистр, ё → е, без крайних пробелов. */
export function normalizeQuery(raw: string): string {
  return raw.trim().toLowerCase().replace(/ё/g, 'е');
}

/** Подсказки: с 2 символов, совпадение с начала названия, не больше 10, в порядке cities. */
export function suggestCities(cities: readonly FormCity[], query: string): FormCity[] {
  const q = normalizeQuery(query);
  if (q.length < SUGGEST_MIN_CHARS) return [];
  const out: FormCity[] = [];
  for (const c of cities) {
    if (normalizeQuery(c[0]).startsWith(q)) {
      out.push(c);
      if (out.length >= SUGGEST_LIMIT) break;
    }
  }
  return out;
}

/** Строки подсказки: город; ниже регион. Регион = город (Москва и др.) → одна строка. */
export function cityLines(city: FormCity): string[] {
  const [name, region] = city;
  return region === name || region === '' ? [name] : [name, region];
}

export type WeightRange = Pick<FormConfig['weight'], 'min' | 'max'>;

/** Запятая → точка, не больше 1 знака после точки, min ≤ x ≤ max; иначе null. */
export function parseWeight(raw: string, range: WeightRange): number | null {
  const s = raw.trim().replace(',', '.');
  if (!/^\d+(\.\d)?$/.test(s)) return null;
  const x = Number(s);
  if (!Number.isFinite(x) || x < range.min || x > range.max) return null;
  return x;
}

// ---- Состояние формы ----

export interface FormState {
  screen: 'fields' | 'confirm';
  /** Текст в поле города. */
  query: string;
  /** Выбранный пояс (IANA) или null — выбора нет. */
  tz: string | null;
  /** Подпись выбранного места для сводки (город из подсказок или город пояса). */
  place: string;
  /** Открыт ли список «Моего города нет». */
  fallbackOpen: boolean;
  gender: FormGender | null;
  wellbeing: string | null;
  weightText: string;
}

export const INITIAL_FORM: FormState = {
  screen: 'fields',
  query: '',
  tz: null,
  place: '',
  fallbackOpen: false,
  gender: null,
  wellbeing: null,
  weightText: '',
};

export type FormAction =
  | { type: 'setQuery'; query: string }
  | { type: 'pickCity'; city: string; tz: string }
  | { type: 'openFallback' }
  | { type: 'pickTz'; tz: string; place: string }
  | { type: 'setGender'; gender: FormGender }
  | { type: 'setWellbeing'; code: string }
  | { type: 'setWeight'; text: string }
  | { type: 'confirm'; weight: WeightRange }
  | { type: 'edit' };

/** Заданы tz, пол, самочувствие и верный вес — можно открыть «всё верно?». */
export function canConfirm(state: FormState, weight: WeightRange): boolean {
  return (
    state.tz !== null &&
    state.gender !== null &&
    state.wellbeing !== null &&
    parseWeight(state.weightText, weight) !== null
  );
}

export function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.type) {
    case 'setQuery':
      // Правка текста сбрасывает выбор.
      return { ...state, query: action.query, tz: null, place: '' };
    case 'pickCity':
      return { ...state, query: action.city, tz: action.tz, place: action.city, fallbackOpen: false };
    case 'openFallback':
      return { ...state, fallbackOpen: true };
    case 'pickTz':
      return { ...state, tz: action.tz, place: action.place };
    case 'setGender':
      return { ...state, gender: action.gender };
    case 'setWellbeing':
      return { ...state, wellbeing: action.code };
    case 'setWeight':
      return { ...state, weightText: action.text };
    case 'confirm':
      if (state.screen !== 'fields' || !canConfirm(state, action.weight)) return state;
      return { ...state, screen: 'confirm' };
    case 'edit':
      return { ...state, screen: 'fields' };
    default:
      return state;
  }
}

/** Тело POST ровно {tz, gender, wellbeing_code, weight_kg}; города нет (Р-16). Не готово → null. */
export function buildFormBody(state: FormState, weight: WeightRange): FormBody | null {
  const kg = parseWeight(state.weightText, weight);
  if (state.tz === null || state.gender === null || state.wellbeing === null || kg === null) return null;
  return { tz: state.tz, gender: state.gender, wellbeing_code: state.wellbeing, weight_kg: kg };
}

export type FormErrorAction = 'done' | 'conflict' | 'restart' | 'invalid' | 'retry';

/**
 * Что делать после ошибки запроса анкеты:
 * 409 ONBOARDING_FORM_EXISTS → done; 409 IDEMPOTENCY_CONFLICT → conflict (новый op_id);
 * 404 и 409 RECONSENT_REQUIRED → restart; 422 → invalid; прочее (401, 429, 503, сеть) → retry.
 */
export function formErrorAction(err: unknown): FormErrorAction {
  if (!(err instanceof ApiError)) return 'retry';
  if (err.status === 404) return 'restart';
  if (err.status === 409) {
    if (err.code === 'ONBOARDING_FORM_EXISTS') return 'done';
    if (err.code === 'IDEMPOTENCY_CONFLICT') return 'conflict';
    if (err.code === 'RECONSENT_REQUIRED') return 'restart';
    return 'retry';
  }
  if (err.status === 422) return 'invalid';
  return 'retry';
}
