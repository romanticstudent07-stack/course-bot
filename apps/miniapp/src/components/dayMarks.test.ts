// apps/miniapp/src/components/dayMarks.test.ts — vitest, environment node.
// Отметки и отчёт дня (day-screen-b): подписи, «все отмечены», можно ли нажать / отправить,
// тело отчёта, тот же X-Client-Op-Id при повторе, действия и сообщения после ошибок.
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type DayBlock, type DayCurrent } from '../api/client.ts';
import {
  DAY_ALREADY_SUBMITTED_MESSAGE,
  DAY_CHANGED_MESSAGE,
  DAY_CLOSED_MESSAGE,
  DAY_NOT_ACTIVE_MESSAGE,
  actionMessage,
  allMarked,
  canPressMark,
  canSendReport,
  markErrorAction,
  markLabels,
  marksFromDay,
  reportBody,
  reuseOpId,
  submitErrorAction,
} from './dayMarks.ts';
import { errorMessage } from './OnboardingFlow.tsx';

const block = (n: number, extra: Partial<DayBlock> = {}): DayBlock => ({
  block_id: `b${n}`,
  title_key: `D.title_${n}`,
  help_key: `D.help_${n}`,
  critical: false,
  mark: null,
  ...extra,
});

const openDay = (extra: Partial<DayCurrent> = {}): DayCurrent => ({
  status: 'open',
  lives: 3,
  test_entry: false,
  position: { stage_no: 1, module_no: 1, day_no: 1 },
  day_started_at: '2026-10-22T04:00:00+03:00',
  blocks: [block(1), block(2)],
  active_from: '2026-10-22T04:00:00+03:00',
  deadline_at: '2026-10-23T00:00:00+03:00',
  queued_until: null,
  buttons_active: true,
  ...extra,
});

const idle = { sending: false, sent: false };
const both = { b1: 'done', b2: 'not_done' } as const;

describe('markLabels', () => {
  it('done / not_done / null', () => {
    expect(markLabels('done')).toEqual({ done: '✅ Выполнил', notDone: 'Не выполнил' });
    expect(markLabels('not_done')).toEqual({ done: 'Выполнил', notDone: '⬜ Не выполнил' });
    expect(markLabels(null)).toEqual({ done: 'Выполнил', notDone: 'Не выполнил' });
  });
});

describe('marksFromDay', () => {
  it('null пропускается', () => {
    const day = openDay({ blocks: [block(1, { mark: 'done' }), block(2), block(3, { mark: 'not_done' })] });
    expect(marksFromDay(day)).toEqual({ b1: 'done', b3: 'not_done' });
  });
  it('нет блоков / нет дня → пусто', () => {
    expect(marksFromDay(openDay({ blocks: null }))).toEqual({});
    expect(marksFromDay(null)).toEqual({});
  });
});

describe('allMarked', () => {
  const blocks = [block(1), block(2)];
  it('пусто, часть, все', () => {
    expect(allMarked([], {})).toBe(false);
    expect(allMarked(blocks, {})).toBe(false);
    expect(allMarked(blocks, { b1: 'done' })).toBe(false);
    expect(allMarked(blocks, both)).toBe(true);
  });
});

describe('canPressMark / canSendReport', () => {
  it('open + buttons_active true → да', () => {
    expect(canPressMark('open', openDay(), idle)).toBe(true);
    expect(canSendReport('open', openDay(), idle, both)).toBe(true);
  });
  it('not_active, closed, queued → нет', () => {
    const inactive = openDay({ buttons_active: false });
    expect(canPressMark('not_active', inactive, idle)).toBe(false);
    expect(canSendReport('not_active', inactive, idle, both)).toBe(false);
    expect(canPressMark('closed', openDay({ status: 'closed', buttons_active: false }), idle)).toBe(false);
    expect(canPressMark('queued', openDay({ status: 'queued', buttons_active: false }), idle)).toBe(false);
    expect(canSendReport('queued', openDay({ status: 'queued' }), idle, both)).toBe(false);
  });
  it('open, но buttons_active не true → нет', () => {
    expect(canPressMark('open', openDay({ buttons_active: null }), idle)).toBe(false);
    expect(canPressMark('open', null, idle)).toBe(false);
  });
  it('sending, sent → нет', () => {
    expect(canPressMark('open', openDay(), { sending: true, sent: false })).toBe(false);
    expect(canPressMark('open', openDay(), { sending: false, sent: true })).toBe(false);
    expect(canSendReport('open', openDay(), { sending: true, sent: false }, both)).toBe(false);
    expect(canSendReport('open', openDay(), { sending: false, sent: true }, both)).toBe(false);
  });
  it('не все отмечены → отправить нельзя', () => {
    expect(canSendReport('open', openDay(), idle, { b1: 'done' })).toBe(false);
  });
});

describe('reportBody', () => {
  it('порядок блоков, не порядок ключей отметок', () => {
    const blocks = [block(2), block(1), block(3)];
    const marks = { b1: 'done', b3: 'not_done', b2: 'done' } as const;
    expect(reportBody(blocks, marks)).toEqual({
      marks: [
        { block_id: 'b2', value: 'done' },
        { block_id: 'b1', value: 'done' },
        { block_id: 'b3', value: 'not_done' },
      ],
    });
  });
});

describe('reuseOpId', () => {
  const body = { marks: [{ block_id: 'b1', value: 'done' }] };
  it('первый раз → новый id', () => {
    const makeId = vi.fn(() => 'op-1');
    expect(reuseOpId(null, body, makeId)).toEqual({ opId: 'op-1', key: JSON.stringify(body) });
    expect(makeId).toHaveBeenCalledTimes(1);
  });
  it('то же тело → тот же opId, makeId не вызван', () => {
    const prev = { opId: 'op-1', key: JSON.stringify(body) };
    const makeId = vi.fn(() => 'op-2');
    expect(reuseOpId(prev, { marks: [{ block_id: 'b1', value: 'done' }] }, makeId)).toBe(prev);
    expect(makeId).not.toHaveBeenCalled();
  });
  it('другое тело → новый opId', () => {
    const prev = { opId: 'op-1', key: JSON.stringify(body) };
    const makeId = vi.fn(() => 'op-2');
    const other = { marks: [{ block_id: 'b1', value: 'not_done' }] };
    expect(reuseOpId(prev, other, makeId)).toEqual({ opId: 'op-2', key: JSON.stringify(other) });
    expect(makeId).toHaveBeenCalledTimes(1);
  });
});

const DAY_409 = ['DAY_NOT_STARTED', 'DAY_NOT_ACTIVE', 'DAY_CLOSED', 'DAY_ALREADY_SUBMITTED'];

describe('markErrorAction', () => {
  it('409 дня и 422 BLOCK_NOT_IN_DAY → refetch', () => {
    for (const code of DAY_409) expect(markErrorAction(new ApiError(409, code, ''))).toBe('refetch');
    expect(markErrorAction(new ApiError(422, 'BLOCK_NOT_IN_DAY', ''))).toBe('refetch');
  });
  it('прочее → retry', () => {
    expect(markErrorAction(new ApiError(422, 'VALIDATION_ERROR', ''))).toBe('retry');
    expect(markErrorAction(new ApiError(409, 'OTHER', ''))).toBe('retry');
    expect(markErrorAction(new ApiError(503, 'SERVICE_UNAVAILABLE', ''))).toBe('retry');
    expect(markErrorAction(new ApiError(401, 'TG_INIT_INVALID', ''))).toBe('retry');
    expect(markErrorAction(new TypeError('Failed to fetch'))).toBe('retry');
  });
});

describe('submitErrorAction', () => {
  it('409 дня и 422 MARKS_INCOMPLETE → refetch', () => {
    for (const code of DAY_409) expect(submitErrorAction(new ApiError(409, code, ''))).toBe('refetch');
    expect(submitErrorAction(new ApiError(422, 'MARKS_INCOMPLETE', ''))).toBe('refetch');
  });
  it('409 IDEMPOTENCY_CONFLICT → new_op_refetch', () => {
    expect(submitErrorAction(new ApiError(409, 'IDEMPOTENCY_CONFLICT', ''))).toBe('new_op_refetch');
  });
  it('401, 429, 503, сеть, прочее → retry', () => {
    expect(submitErrorAction(new ApiError(401, 'TG_INIT_INVALID', ''))).toBe('retry');
    expect(submitErrorAction(new ApiError(429, 'RATE_LIMITED', ''))).toBe('retry');
    expect(submitErrorAction(new ApiError(503, 'SERVICE_UNAVAILABLE', ''))).toBe('retry');
    expect(submitErrorAction(new ApiError(422, 'BLOCK_NOT_IN_DAY', ''))).toBe('retry');
    expect(submitErrorAction(new TypeError('Failed to fetch'))).toBe('retry');
  });
});

describe('actionMessage', () => {
  it('DAY_CLOSED, DAY_NOT_ACTIVE, DAY_ALREADY_SUBMITTED', () => {
    expect(actionMessage(new ApiError(409, 'DAY_CLOSED', ''), 'report')).toBe(DAY_CLOSED_MESSAGE);
    expect(actionMessage(new ApiError(409, 'DAY_NOT_ACTIVE', ''), 'mark')).toBe(DAY_NOT_ACTIVE_MESSAGE);
    expect(actionMessage(new ApiError(409, 'DAY_ALREADY_SUBMITTED', ''), 'mark')).toBe(
      DAY_ALREADY_SUBMITTED_MESSAGE,
    );
  });
  it('день обновился', () => {
    for (const [status, code] of [
      [409, 'DAY_NOT_STARTED'],
      [422, 'BLOCK_NOT_IN_DAY'],
      [422, 'MARKS_INCOMPLETE'],
      [409, 'IDEMPOTENCY_CONFLICT'],
    ] as const) {
      expect(actionMessage(new ApiError(status, code, ''), 'report')).toBe(DAY_CHANGED_MESSAGE);
    }
  });
  it('прочее — с префиксом', () => {
    const e503 = new ApiError(503, 'SERVICE_UNAVAILABLE', '');
    expect(actionMessage(e503, 'mark')).toBe(`Отметка не сохранилась. ${errorMessage(e503)}`);
    const net = new TypeError('Failed to fetch');
    expect(actionMessage(net, 'report')).toBe(`Отчёт не отправлен. ${errorMessage(net)}`);
  });
});
