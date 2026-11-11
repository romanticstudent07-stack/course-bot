// apps/miniapp/src/components/checkup.ts — чистые функции экрана onb.checkup (miniapp-i3-1b).
//
// Без React и без запросов (тесты — vitest, environment node). Экран — Checkup.tsx.
// Вопросы по одному, только кнопки scale.min…scale.max (0–3), ручного ввода баллов нет (05 Fail-safe).
// Идемпотентность кнопок: ответ несёт номер вопроса; номер не текущий → игнор.
// Ответы и зона живут только в state React: не на устройство, не в лог, не в URL (Р-18, 2А).
import {
  ApiError,
  type CheckupConfig,
  type CheckupQuestion,
  type CheckupSubmitBody,
} from '../api/client.ts';

export interface CheckupState {
  /** Число вопросов (questions.length из config). */
  total: number;
  /** Текущий вопрос (0…total-1); total — экран «ответы готовы». */
  index: number;
  /** Ответ на каждый вопрос; null — ещё нет. */
  answers: (number | null)[];
}

export function initialCheckup(total: number): CheckupState {
  return { total, index: 0, answers: Array.from({ length: total }, () => null) };
}

export type CheckupAction = { type: 'answer'; index: number; value: number } | { type: 'fix' };

export function checkupReducer(state: CheckupState, action: CheckupAction): CheckupState {
  switch (action.type) {
    case 'answer': {
      // Двойное нажатие / устаревшая кнопка: номер не текущий → без изменений.
      if (action.index !== state.index || state.index >= state.total) return state;
      const answers = state.answers.slice();
      answers[state.index] = action.value;
      return { ...state, index: state.index + 1, answers };
    }
    case 'fix':
      // «Исправить»: на предыдущий вопрос, прежний ответ сохранён (будет отмечен).
      if (state.index <= 0) return state;
      return { ...state, index: state.index - 1 };
    default:
      return state;
  }
}

export function questionLabel(index: number, total: number): string {
  return `Вопрос ${index + 1} из ${total}`;
}

export function blockTitle(config: Pick<CheckupConfig, 'blocks'>, question: Pick<CheckupQuestion, 'block'>): string {
  return config.blocks.find((b) => b.id === question.block)?.title ?? '';
}

/** Кнопки шкалы: от min до max включительно. */
export function scaleValues(scale: CheckupConfig['scale']): number[] {
  const out: number[] = [];
  for (let v = scale.min; v <= scale.max; v += 1) out.push(v);
  return out;
}

export const DEFAULT_SCALE: CheckupConfig['scale'] = { min: 0, max: 3 };

/** Тело POST: все ответы — целые в шкале; не хватает хотя бы одного → null. */
export function buildSubmitBody(
  state: CheckupState,
  scale: CheckupConfig['scale'] = DEFAULT_SCALE,
): CheckupSubmitBody | null {
  if (state.total <= 0 || state.answers.length !== state.total) return null;
  const answers: number[] = [];
  for (const a of state.answers) {
    if (a === null || !Number.isInteger(a) || a < scale.min || a > scale.max) return null;
    answers.push(a);
  }
  return { occasion: 'onboarding', answers };
}

export type CheckupErrorAction = 'done' | 'conflict' | 'restart' | 'invalid' | 'retry';

/**
 * Что делать после ошибки запроса Чек-Апа:
 * 409 CHECKUP_EXISTS → done; 409 IDEMPOTENCY_CONFLICT → conflict (новый op_id);
 * 404 и 409 RECONSENT_REQUIRED → restart; 422 → invalid; прочее (401, 429, 503, сеть) → retry.
 */
export function checkupErrorAction(err: unknown): CheckupErrorAction {
  if (!(err instanceof ApiError)) return 'retry';
  if (err.status === 404) return 'restart';
  if (err.status === 409) {
    if (err.code === 'CHECKUP_EXISTS') return 'done';
    if (err.code === 'IDEMPOTENCY_CONFLICT') return 'conflict';
    if (err.code === 'RECONSENT_REQUIRED') return 'restart';
    return 'retry';
  }
  if (err.status === 422) return 'invalid';
  return 'retry';
}

export const ZONE_FALLBACK_TITLE = 'Заглушка: результат сохранён';

export interface ZoneView {
  title: string;
  text: string;
}

/** Итог: title и text зоны из config; балла нет. Неизвестная зона → заглушка. */
export function zoneView(config: Pick<CheckupConfig, 'zones'>, zone: string): ZoneView {
  const z = config.zones.find((item) => item.id === zone);
  return z ? { title: z.title, text: z.text } : { title: ZONE_FALLBACK_TITLE, text: '' };
}
