// apps/miniapp/src/components/dayMarks.ts — чистые функции отметок и отчёта дня (day-screen-b), без React.
//
// DM 3.3: «Выполнил» / «Не выполнил» переключаемо до отправки; «Отправить отчёт» — когда отмечены все.
// DM 3.10: после первого нажатия гаснет. DM 3.11: ложного успеха нет.
// «Можно ли нажать» — только view и buttons_active; окно 04:00–00:00 клиент не считает (коды 409 — от сервера).
import { ApiError, type DayBlock, type DayCurrent, type DayMarkValue, type DayReportIn } from '../api/client.ts';
import type { DayView } from './dayScreen.ts';
import { errorMessage } from './OnboardingFlow.tsx';

export type LocalMarks = Record<string, DayMarkValue>;

export interface DayBusy {
  sending: boolean;
  sent: boolean;
}

/** Отметки из ответа GET (сервер — источник правды); null пропускается. */
export function marksFromDay(day: DayCurrent | null | undefined): LocalMarks {
  const out: LocalMarks = {};
  const blocks = day && Array.isArray(day.blocks) ? day.blocks : [];
  for (const b of blocks) {
    if (b && (b.mark === 'done' || b.mark === 'not_done')) out[b.block_id] = b.mark;
  }
  return out;
}

/** Подписи двух кнопок: выбранная — с эмодзи (визуализация сменой текста, DM 3.3). */
export function markLabels(mark: DayMarkValue | null | undefined): { done: string; notDone: string } {
  return {
    done: mark === 'done' ? '✅ Выполнил' : 'Выполнил',
    notDone: mark === 'not_done' ? '⬜ Не выполнил' : 'Не выполнил',
  };
}

/** Все блоки отмечены (пустой список — нет). */
export function allMarked(blocks: readonly DayBlock[] | null | undefined, marks: LocalMarks): boolean {
  if (!blocks || blocks.length === 0) return false;
  return blocks.every((b) => marks[b.block_id] === 'done' || marks[b.block_id] === 'not_done');
}

export function canPressMark(view: DayView, day: DayCurrent | null | undefined, busy: DayBusy): boolean {
  return view === 'open' && day?.buttons_active === true && !busy.sending && !busy.sent;
}

export function canSendReport(
  view: DayView,
  day: DayCurrent | null | undefined,
  busy: DayBusy,
  marks: LocalMarks,
): boolean {
  return canPressMark(view, day, busy) && allMarked(day?.blocks, marks);
}

/** Тело отчёта: каждый блок ровно один раз, в порядке блоков. */
export function reportBody(blocks: readonly DayBlock[], marks: LocalMarks): DayReportIn {
  return { marks: blocks.map((b) => ({ block_id: b.block_id, value: marks[b.block_id] })) };
}

export interface OpRef {
  opId: string;
  key: string;
}

/** Тот же X-Client-Op-Id для того же тела (повтор); другое тело — новый id. */
export function reuseOpId(prev: OpRef | null, body: unknown, makeId: () => string): OpRef {
  const key = JSON.stringify(body);
  if (prev && prev.key === key) return prev;
  return { opId: makeId(), key };
}

const DAY_409 = new Set(['DAY_NOT_STARTED', 'DAY_NOT_ACTIVE', 'DAY_CLOSED', 'DAY_ALREADY_SUBMITTED']);

export type MarkErrorAction = 'refetch' | 'retry';
export type SubmitErrorAction = 'refetch' | 'new_op_refetch' | 'retry';

export function markErrorAction(err: unknown): MarkErrorAction {
  if (!(err instanceof ApiError)) return 'retry';
  if (err.status === 409 && DAY_409.has(err.code)) return 'refetch';
  if (err.status === 422 && err.code === 'BLOCK_NOT_IN_DAY') return 'refetch';
  return 'retry';
}

/** 'retry' — повтор с тем же opId (401, 429, 503, сеть, прочее). */
export function submitErrorAction(err: unknown): SubmitErrorAction {
  if (!(err instanceof ApiError)) return 'retry';
  if (err.status === 409 && err.code === 'IDEMPOTENCY_CONFLICT') return 'new_op_refetch';
  if (err.status === 409 && DAY_409.has(err.code)) return 'refetch';
  if (err.status === 422 && err.code === 'MARKS_INCOMPLETE') return 'refetch';
  return 'retry';
}

export const DAY_CLOSED_MESSAGE = 'День закрыт: отчёт принимался до 00:00.';
export const DAY_NOT_ACTIVE_MESSAGE = 'Кнопки станут активны в 04:00.';
export const DAY_ALREADY_SUBMITTED_MESSAGE = 'Отчёт уже отправлен.';
export const DAY_CHANGED_MESSAGE = 'День обновился. Проверьте отметки.';
const DAY_CHANGED_CODES = new Set(['DAY_NOT_STARTED', 'BLOCK_NOT_IN_DAY', 'MARKS_INCOMPLETE', 'IDEMPOTENCY_CONFLICT']);

export function actionMessage(err: unknown, kind: 'mark' | 'report'): string {
  if (err instanceof ApiError) {
    if (err.code === 'DAY_CLOSED') return DAY_CLOSED_MESSAGE;
    if (err.code === 'DAY_NOT_ACTIVE') return DAY_NOT_ACTIVE_MESSAGE;
    if (err.code === 'DAY_ALREADY_SUBMITTED') return DAY_ALREADY_SUBMITTED_MESSAGE;
    if (DAY_CHANGED_CODES.has(err.code)) return DAY_CHANGED_MESSAGE;
  }
  return (kind === 'mark' ? 'Отметка не сохранилась. ' : 'Отчёт не отправлен. ') + errorMessage(err);
}
