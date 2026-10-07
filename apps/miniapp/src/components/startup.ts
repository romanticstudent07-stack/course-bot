// apps/miniapp/src/components/startup.ts — решение на старте Mini App (returning-2).
//
// Чистые функции без React (тесты — vitest, environment node).
// Решение «показывать ли экраны 18+ и согласий» принимает СЕРВЕР
// (GET /miniapp/v1/onboarding/status); клиент версии и тексты согласий не сравнивает,
// не смотрит initDataUnsafe и ничего из ответа на устройстве не хранит.
//   - номер — только при status 'returning' с непустым short_no;
//   - reconsent, new, неизвестный status, битое тело → онбординг (безопасная сторона:
//     экраны согласий, решение снова за сервером);
//   - ошибка запроса status → экран «Повторить» (App.tsx): ни номера, ни онбординга.
import type { Draft } from './drafts.ts';
import { errorMessage } from './OnboardingFlow.tsx';

export type StartPhase = 'number' | 'onboarding';
export type AfterNumber = 'later' | 'app';

/** short_no из ответа status, если это returning с непустой строкой; иначе null. */
export function returningShortNo(resp: unknown): string | null {
  if (typeof resp !== 'object' || resp === null) return null;
  const r = resp as { status?: unknown; short_no?: unknown };
  if (r.status !== 'returning') return null;
  if (typeof r.short_no !== 'string' || r.short_no.trim() === '') return null;
  return r.short_no;
}

/** Что показать после ответа status: номер или онбординг. */
export function startPhase(resp: unknown): StartPhase {
  return returningShortNo(resp) === null ? 'onboarding' : 'number';
}

/** Сервер прислал reconsent (онбординг повторяется из-за согласий, pid уже есть). */
export function isReconsent(resp: unknown): boolean {
  if (typeof resp !== 'object' || resp === null) return false;
  return (resp as { status?: unknown }).status === 'reconsent';
}

/**
 * Куда после номера: незаконченный черновик → анкета, иначе → курс.
 * openDraft уже чистит чужой, битый, старше 24 ч и старую метку finished.
 */
export function afterNumber(draft: Draft | null): AfterNumber {
  return draft !== null && draft.step !== 'finished' ? 'later' : 'app';
}

/** Текст экрана «Повторить» при ошибке status — те же формулировки, что в онбординге. */
export function startErrorMessage(err: unknown): string {
  return errorMessage(err);
}
