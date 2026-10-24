// apps/miniapp/src/components/startup.ts — решение на старте Mini App (returning-2).
//
// Чистые функции без React (тесты — vitest, environment node).
// Решение «показывать ли экраны 18+ и согласий» принимает СЕРВЕР
// (GET /miniapp/v1/onboarding/status); клиент версии и тексты согласий не сравнивает,
// не смотрит initDataUnsafe и ничего из ответа на устройстве не хранит.
//   - номер — только при status 'returning' с непустым short_no;
//   - reconsent, new, неизвестный status, битое тело → онбординг (безопасная сторона:
//     экраны согласий, решение снова за сервером);
//   - ошибка запроса status → экран «Повторить» (App.tsx): ни номера, ни онбординга;
//   - no_access (и 403 ACCESS_NOT_GRANTED из first-launch) → экран «доступ не открыт» (Р-2).
import { ApiError } from '../api/client.ts';
import type { Draft } from './drafts.ts';
import { errorMessage } from './OnboardingFlow.tsx';

export type StartPhase = 'number' | 'onboarding' | 'no-access';
export type AfterNumber = 'later' | 'app';

/** short_no из ответа status, если это returning с непустой строкой; иначе null. */
export function returningShortNo(resp: unknown): string | null {
  if (typeof resp !== 'object' || resp === null) return null;
  const r = resp as { status?: unknown; short_no?: unknown };
  if (r.status !== 'returning') return null;
  if (typeof r.short_no !== 'string' || r.short_no.trim() === '') return null;
  return r.short_no;
}

/** Сервер прислал no_access: доступ не выдан (Р-2). */
export function isNoAccess(resp: unknown): boolean {
  if (typeof resp !== 'object' || resp === null) return false;
  return (resp as { status?: unknown }).status === 'no_access';
}

/** Что показать после ответа status: номер, экран «доступ не открыт» или онбординг. */
export function startPhase(resp: unknown): StartPhase {
  if (returningShortNo(resp) !== null) return 'number';
  if (isNoAccess(resp)) return 'no-access';
  return 'onboarding';
}

/** first-launch ответил 403 ACCESS_NOT_GRANTED — доступ не выдан (Р-2). */
export function isAccessNotGranted(err: unknown): boolean {
  return err instanceof ApiError && err.status === 403 && err.code === 'ACCESS_NOT_GRANTED';
}

/** Экран «доступ не открыт» (Р-2): заглушка на «Вы», не через text_registry (D-39). */
export const NO_ACCESS_TEXT =
  'Доступ пока не открыт. Если у Вас есть промокод — отправьте его боту. Когда бот ответит, нажмите «Проверить ещё раз».';
export const NO_ACCESS_BUTTON = 'Проверить ещё раз';

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
