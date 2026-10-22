// apps/miniapp/src/components/dayScreen.test.ts — vitest, environment node.
// Экран /day (day-screen-a): view по status, дата из строки сервера, ключи текстов,
// задержки повторного GET, сообщения ошибок и действия после ошибки тестового входа.
import { describe, expect, it } from 'vitest';

import { ApiError, type DayBlock, type DayCurrent } from '../api/client.ts';
import {
  DAY_TEXT_KEYS,
  PARTICIPANT_NOT_FOUND_MESSAGE,
  dayErrorMessage,
  dayTextKeys,
  dayView,
  refetchDelayMs,
  testEnterAction,
  wallClock,
} from './dayScreen.ts';

const block = (n: number, extra: Partial<DayBlock> = {}): DayBlock => ({
  block_id: `b${n}`,
  title_key: `D.title_${n}`,
  help_key: `D.help_${n}`,
  critical: false,
  mark: null,
  ...extra,
});

const base3 = { lives: 3, test_entry: false };
const withDay = (status: DayCurrent['status'], extra: Partial<DayCurrent> = {}): DayCurrent => ({
  status,
  ...base3,
  position: { stage_no: 1, module_no: 1, day_no: 1 },
  blocks: [block(1)],
  active_from: '2026-10-22T04:00:00+03:00',
  deadline_at: '2026-10-23T00:00:00+03:00',
  queued_until: null,
  buttons_active: true,
  ...extra,
});

const THREE = [DAY_TEXT_KEYS.activeFromHint, DAY_TEXT_KEYS.queueWait, DAY_TEXT_KEYS.closedHint];

describe('dayView', () => {
  it('6 статусов', () => {
    expect(dayView({ status: 'not_started', ...base3 })).toBe('not_started');
    expect(dayView({ status: 'entering', ...base3 })).toBe('entering');
    expect(dayView(withDay('open'))).toBe('open');
    expect(dayView(withDay('submitted'))).toBe('submitted');
    expect(dayView(withDay('queued', { blocks: null, buttons_active: false }))).toBe('queued');
    expect(dayView(withDay('closed'))).toBe('closed');
  });

  it('not_started + test_entry → test_entry', () => {
    expect(dayView({ status: 'not_started', lives: 3, test_entry: true })).toBe('test_entry');
  });

  it('open без buttons_active или false → not_active', () => {
    const noFlag: Record<string, unknown> = { ...withDay('open') };
    delete noFlag.buttons_active;
    expect(dayView(noFlag)).toBe('not_active');
    expect(dayView(withDay('open', { buttons_active: false }))).toBe('not_active');
  });

  it('битое тело, незнакомый status, open без blocks → unknown', () => {
    expect(dayView(null)).toBe('unknown');
    expect(dayView({})).toBe('unknown');
    expect(dayView({ status: 'x' })).toBe('unknown');
    expect(dayView(withDay('open', { blocks: null }))).toBe('unknown');
    expect(dayView(withDay('closed', { blocks: undefined }))).toBe('unknown');
    expect(dayView(withDay('submitted', { blocks: null }))).toBe('unknown');
  });
});

describe('wallClock', () => {
  it('дата и время из строки со сдвигом', () => {
    expect(wallClock('2026-10-22T04:00:00+03:00')).toEqual({ date: '22.10', time: '04:00' });
  });

  it('дробь секунд и Z — по строке, без пересчёта пояса', () => {
    expect(wallClock('2026-10-22T04:00:00.123456+05:00')).toEqual({ date: '22.10', time: '04:00' });
    expect(wallClock('2026-01-05T23:59:00Z')).toEqual({ date: '05.01', time: '23:59' });
  });

  it('плохая строка и undefined → null', () => {
    expect(wallClock('плохо')).toBeNull();
    expect(wallClock(undefined)).toBeNull();
  });
});

describe('dayTextKeys', () => {
  it('3 ключа + ключи блоков без повторов, порядок стабилен', () => {
    const day = withDay('open', {
      blocks: [block(1), block(2), block(3, { title_key: 'D.title_1', help_key: 'D.help_2' })],
    });
    expect(dayTextKeys(day)).toEqual([...THREE, 'D.title_1', 'D.help_1', 'D.title_2', 'D.help_2']);
  });

  it('queued (blocks null) → только 3', () => {
    expect(dayTextKeys(withDay('queued', { blocks: null }))).toEqual(THREE);
  });
});

describe('refetchDelayMs', () => {
  const now = Date.parse('2026-10-22T03:00:00+03:00');

  it('queued → до queued_until + 1 с', () => {
    const day = withDay('queued', { blocks: null, queued_until: '2026-10-22T03:10:00+03:00' });
    expect(refetchDelayMs(day, now, 0)).toBe(10 * 60_000 + 1000);
  });

  it('цель в прошлом → 1000', () => {
    const day = withDay('queued', { blocks: null, queued_until: '2026-10-22T02:00:00+03:00' });
    expect(refetchDelayMs(day, now, 0)).toBe(1000);
  });

  it('цель дальше 24 ч → 86 400 000', () => {
    const day = withDay('queued', { blocks: null, queued_until: '2026-10-25T03:00:00+03:00' });
    expect(refetchDelayMs(day, now, 0)).toBe(86_400_000);
  });

  it('not_active → active_from', () => {
    const day = withDay('open', { buttons_active: false, active_from: '2026-10-22T04:00:00+03:00' });
    expect(refetchDelayMs(day, now, 0)).toBe(3_600_000 + 1000);
  });

  it('open → deadline_at', () => {
    const day = withDay('open', { deadline_at: '2026-10-22T05:00:00+03:00' });
    expect(refetchDelayMs(day, now, 0)).toBe(2 * 3_600_000 + 1000);
  });

  it('пояс телефона не влияет: та же точка в Z', () => {
    const day = withDay('open', { deadline_at: '2026-10-22T02:00:00Z' });
    expect(refetchDelayMs(day, now, 0)).toBe(2 * 3_600_000 + 1000);
  });

  it('closed → 60 000', () => {
    expect(refetchDelayMs(withDay('closed'), now, 0)).toBe(60_000);
  });

  it('submitted: tries 0–4 → 2000, 5 → null', () => {
    for (let i = 0; i < 5; i++) expect(refetchDelayMs(withDay('submitted'), now, i)).toBe(2000);
    expect(refetchDelayMs(withDay('submitted'), now, 5)).toBeNull();
  });

  it('entering: tries 0 → 2000, 5 → null', () => {
    expect(refetchDelayMs({ status: 'entering', ...base3 }, now, 0)).toBe(2000);
    expect(refetchDelayMs({ status: 'entering', ...base3 }, now, 5)).toBeNull();
  });

  it('not_started, test_entry, unknown → null', () => {
    expect(refetchDelayMs({ status: 'not_started', ...base3 }, now, 0)).toBeNull();
    expect(refetchDelayMs({ status: 'not_started', lives: 3, test_entry: true }, now, 0)).toBeNull();
    expect(refetchDelayMs(null, now, 0)).toBeNull();
  });

  it('битая дата → null', () => {
    expect(refetchDelayMs(withDay('open', { deadline_at: 'плохо' }), now, 0)).toBeNull();
    expect(refetchDelayMs(withDay('queued', { blocks: null, queued_until: null }), now, 0)).toBeNull();
  });
});

describe('dayErrorMessage', () => {
  it('404 PARTICIPANT_NOT_FOUND → участник не найден', () => {
    expect(dayErrorMessage(new ApiError(404, 'PARTICIPANT_NOT_FOUND', 'x'))).toBe(PARTICIPANT_NOT_FOUND_MESSAGE);
  });

  it('503 → как errorMessage', () => {
    expect(dayErrorMessage(new ApiError(503, 'DAY_CONTENT_MISSING', 'x'))).toBe(
      'Сервис временно недоступен. Попробуйте чуть позже.',
    );
  });

  it('сеть → текст про интернет', () => {
    expect(dayErrorMessage(new TypeError('Failed to fetch'))).toBe(
      'Не удалось связаться с сервером. Проверьте интернет и нажмите «Повторить».',
    );
  });
});

describe('testEnterAction', () => {
  it('404 NOT_FOUND → refetch', () => {
    expect(testEnterAction(new ApiError(404, 'NOT_FOUND', 'x'))).toBe('refetch');
  });

  it('409 DAY_STATE_SYNCING → retry_1s', () => {
    expect(testEnterAction(new ApiError(409, 'DAY_STATE_SYNCING', 'x'))).toBe('retry_1s');
  });

  it('409 RECONSENT_REQUIRED → reopen', () => {
    expect(testEnterAction(new ApiError(409, 'RECONSENT_REQUIRED', 'x'))).toBe('reopen');
  });

  it('прочее → error', () => {
    expect(testEnterAction(new ApiError(404, 'PARTICIPANT_NOT_FOUND', 'x'))).toBe('error');
    expect(testEnterAction(new ApiError(503, 'SERVICE_UNAVAILABLE', 'x'))).toBe('error');
    expect(testEnterAction(new TypeError('Failed to fetch'))).toBe('error');
  });
});
