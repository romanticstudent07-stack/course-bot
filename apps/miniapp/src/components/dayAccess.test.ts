// apps/miniapp/src/components/dayAccess.test.ts — vitest, environment node, без DOM (miniapp-pause-c3a §9).
import { readFileSync } from 'node:fs';

import { describe, expect, it, vi } from 'vitest';

import { ApiError, type PauseOut, type PauseStatus } from '../api/client.ts';
import { canRetry, checkDayAccess, retryAtFrom, type DayAccess } from './dayAccess.ts';
import { PAUSE_STATUS_ACTIVE, PAUSE_STATUS_CANCELLABLE } from './pause.ts';

const NOW = 1_800_000_000_000;

function pauseOf(status: string): PauseOut {
  return {
    id: 7,
    status,
    start_at: '2026-11-27T00:00:00+03:00',
    planned_end_at: '2026-11-30T00:00:00+03:00',
  };
}

function statusWith(pause: PauseOut | null): PauseStatus {
  return {
    budget_days_left: 14,
    budget_days_total: 14,
    cycle_ends_at: null,
    pause,
    can_request: pause === null,
    refusal: pause === null ? null : 'already_open',
    start_date: '2026-11-27',
  };
}

function okGet(pause: PauseOut | null) {
  return vi.fn(async () => statusWith(pause));
}

function failGet(err: unknown) {
  return vi.fn(async (): Promise<PauseStatus> => {
    throw err;
  });
}

function retryAtOf(access: DayAccess): number {
  if (access.kind !== 'error') throw new Error(`ожидался error, пришёл ${access.kind}`);
  return access.retryAt;
}

describe('константы статусов (pause.py:112–113)', () => {
  it('ACTIVE и CANCELLABLE', () => {
    expect(PAUSE_STATUS_ACTIVE).toBe('active');
    expect([...PAUSE_STATUS_CANCELLABLE]).toEqual(['requested', 'approved']);
  });
});

describe('checkDayAccess: статус паузы', () => {
  it('active → paused, get вызван ровно 1 раз', async () => {
    const get = okGet(pauseOf('active'));
    expect(await checkDayAccess(get, NOW)).toEqual({ kind: 'paused' });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('requested и approved → open, get вызван ровно 1 раз', async () => {
    for (const s of PAUSE_STATUS_CANCELLABLE) {
      const get = okGet(pauseOf(s));
      expect(await checkDayAccess(get, NOW)).toEqual({ kind: 'open' });
      expect(get).toHaveBeenCalledTimes(1);
    }
  });

  it('pause null → open, get вызван ровно 1 раз', async () => {
    const get = okGet(null);
    expect(await checkDayAccess(get, NOW)).toEqual({ kind: 'open' });
    expect(get).toHaveBeenCalledTimes(1);
  });
});

describe('checkDayAccess: ошибки и Retry-After', () => {
  it('сеть → error, retryAt = now', async () => {
    const err = new TypeError('Failed to fetch');
    const get = failGet(err);
    const access = await checkDayAccess(get, NOW);
    expect(access).toEqual({ kind: 'error', error: err, retryAt: NOW });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('503 → error, retryAt = now', async () => {
    const access = await checkDayAccess(failGet(new ApiError(503, 'SERVICE_UNAVAILABLE', '')), NOW);
    expect(retryAtOf(access)).toBe(NOW);
  });

  it('429 с retryAfter 30 → retryAt = now + 30 000', async () => {
    const access = await checkDayAccess(failGet(new ApiError(429, 'RATE_LIMITED', '', 30)), NOW);
    expect(retryAtOf(access)).toBe(NOW + 30_000);
  });

  it('retryAtFrom: 429 без retryAfter и не-429 с retryAfter → now', () => {
    expect(retryAtFrom(new ApiError(429, 'RATE_LIMITED', ''), NOW)).toBe(NOW);
    expect(retryAtFrom(new ApiError(503, 'SERVICE_UNAVAILABLE', '', 30), NOW)).toBe(NOW);
    expect(retryAtFrom(undefined, NOW)).toBe(NOW);
  });
});

describe('canRetry', () => {
  it('до срока false, с срока true', async () => {
    const access = await checkDayAccess(failGet(new ApiError(429, 'RATE_LIMITED', '', 30)), NOW);
    expect(canRetry(access, NOW + 29_999)).toBe(false);
    expect(canRetry(access, NOW + 30_000)).toBe(true);
  });

  it('open и paused → false', () => {
    expect(canRetry({ kind: 'open' }, NOW)).toBe(false);
    expect(canRetry({ kind: 'paused' }, NOW)).toBe(false);
  });

  it('из error никакой now не даёт open без нового checkDayAccess', async () => {
    const get = failGet(new ApiError(429, 'RATE_LIMITED', '', 30));
    const access = await checkDayAccess(get, NOW);
    for (const n of [NOW, NOW + 30_000, NOW + 86_400_000, Number.MAX_SAFE_INTEGER]) {
      canRetry(access, n);
      expect(access.kind).toBe('error');
    }
    expect(get).toHaveBeenCalledTimes(1);
    const next = okGet(null);
    expect(await checkDayAccess(next, NOW + 30_000)).toEqual({ kind: 'open' });
    expect(next).toHaveBeenCalledTimes(1);
  });
});

describe('dayAccess.ts: без таймеров и часов', () => {
  it('в исходнике нет setTimeout, setInterval и Date.now', () => {
    const text = readFileSync(new URL('./dayAccess.ts', import.meta.url), 'utf8');
    for (const banned of ['setTimeout', 'setInterval', 'Date.now']) {
      expect(text.includes(banned), banned).toBe(false);
    }
  });
});
