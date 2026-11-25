// Тесты координатора паузы (miniapp-pause-c1, T5-C1): фейковые getPause, очередь, now и schedule.

import { describe, expect, it } from 'vitest';

import { ApiError, type PauseOut, type PauseStatus } from '../api/client.ts';
import {
  PAUSE_CONFLICT_TEXT,
  PAUSE_REOPEN_TEXT,
  PAUSE_START_SERIES_STEP_MS,
  createPauseCoordinator,
  type PauseView,
} from './pause.ts';
import type { PauseOpArgs, PauseOpKind } from './pauseQueueStore.ts';

const T0 = Date.parse('2026-12-01T00:00:00+03:00');

function status(over: Partial<PauseStatus> = {}): PauseStatus {
  return {
    budget_days_left: 14,
    budget_days_total: 14,
    cycle_ends_at: null,
    pause: null,
    can_request: true,
    refusal: null,
    start_date: '2026-12-02',
    ...over,
  };
}

function pause(over: Partial<PauseOut> = {}): PauseOut {
  return {
    id: 5,
    status: 'approved',
    start_at: new Date(T0).toISOString(),
    planned_end_at: new Date(T0 + 3 * 86_400_000).toISOString(),
    ...over,
  };
}

interface Pending {
  signal: AbortSignal | undefined;
  resolve(v: PauseStatus): void;
  reject(e: unknown): void;
}

interface Timer {
  fn: () => void;
  ms: number;
  cancelled: boolean;
}

function harness() {
  const gets: Pending[] = [];
  const views: PauseView[] = [];
  const enq: Array<[PauseOpKind, PauseOpArgs]> = [];
  const timers: Timer[] = [];
  const clock = { t: T0 };
  const q = { tick: 0, resumeAuth: 0, enqueueThrows: false };
  const c = createPauseCoordinator({
    getPause: (signal) =>
      new Promise<PauseStatus>((resolve, reject) => {
        gets.push({ signal, resolve, reject });
      }),
    queue: {
      enqueue: async (kind, args) => {
        if (q.enqueueThrows) throw new Error('pauseQueue: no owner');
        enq.push([kind, args]);
        return `op-${enq.length}`;
      },
      tick: async () => {
        q.tick += 1;
      },
      resumeAuth: () => {
        q.resumeAuth += 1;
      },
    },
    onView: (v) => views.push(v),
    now: () => clock.t,
    schedule: (fn, ms) => {
      const t: Timer = { fn, ms, cancelled: false };
      timers.push(t);
      return () => {
        t.cancelled = true;
      };
    },
  });
  const last = () => views[views.length - 1] as PauseView;
  /** Отвечает на последний GET и ждёт применения. */
  const answer = async (v: PauseStatus, i = gets.length - 1) => {
    gets[i]?.resolve(v);
    await flush();
  };
  /** Запускает следующий живой таймер. */
  const fire = async () => {
    const t = timers.find((x) => !x.cancelled);
    if (!t) return false;
    t.cancelled = true;
    t.fn();
    await flush();
    return true;
  };
  return { c, gets, views, enq, timers, clock, q, last, answer, fire };
}

/** Ждёт все микрозадачи: один макротакт настоящего setTimeout (только в тесте). */
const flush = () => new Promise<void>((r) => setTimeout(r, 0));

describe('pause coordinator', () => {
  it('(1) два reread, первый ответ пришёл позже — применён только второй, первый получил abort', async () => {
    const h = harness();
    const r1 = h.c.reread();
    const r2 = h.c.reread();
    expect(h.gets[0]?.signal?.aborted).toBe(true);
    h.gets[1]?.resolve(status({ start_date: '2026-12-09' }));
    await r2;
    h.gets[0]?.resolve(status({ start_date: '2026-12-01' }));
    await r1;
    expect(h.last().data?.start_date).toBe('2026-12-09');
  });

  it('(2) двойной request до исхода → один enqueue', async () => {
    const h = harness();
    const r = h.c.reread();
    await h.answer(status());
    await r;
    await Promise.all([h.c.request(3), h.c.request(3)]);
    expect(h.enq).toHaveLength(1);
  });

  it('(3) start_date из последнего применённого GET попадает в args', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status({ start_date: '2026-12-02' }));
    void h.c.reread();
    await h.answer(status({ start_date: '2026-12-03' }));
    await h.c.request(4);
    expect(h.enq).toEqual([['request', { days: 4, start_date: '2026-12-03' }]]);
    expect(h.q.tick).toBe(1);
  });

  it('(4) GET не было или can_request = false → enqueue 0', async () => {
    const h = harness();
    expect(await h.c.request(2)).toBe(false);
    void h.c.reread();
    await h.answer(status({ can_request: false, refusal: 'already_open' }));
    expect(await h.c.request(2)).toBe(false);
    expect(h.enq).toEqual([]);
  });

  it('(5) start_date_passed → reread, enqueue не повторяется', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status());
    await h.c.request(3);
    const before = h.gets.length;
    h.c.onOutcome({ type: 'business', code: 'PAUSE_REFUSED', details: { reason: 'start_date_passed' } });
    expect(h.gets.length).toBe(before + 1);
    expect(h.last().confirmStart).toBe(true);
    await h.answer(status({ start_date: '2026-12-03' }));
    expect(h.enq).toHaveLength(1);
  });

  it('(6) stopped → reread; новый request → новый enqueue', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status());
    await h.c.request(3);
    const before = h.gets.length;
    h.c.onOutcome({ type: 'stopped', status: 422, code: 'VALIDATION_ERROR' });
    expect(h.gets.length).toBe(before + 1);
    await h.answer(status());
    await h.c.request(2);
    expect(h.enq).toHaveLength(2);
  });

  it('(7) enqueue бросает → заглушка, tick 0', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status());
    h.q.enqueueThrows = true;
    expect(await h.c.request(3)).toBe(false);
    expect(h.last().message).toBe(PAUSE_REOPEN_TEXT);
    expect(h.q.tick).toBe(0);
  });

  it('(8) успешный GET → resumeAuth 1 раз; ошибка GET → 0', async () => {
    const ok = harness();
    void ok.c.reread();
    await ok.answer(status());
    expect(ok.q.resumeAuth).toBe(1);

    const bad = harness();
    void bad.c.reread();
    bad.gets[0]?.reject(new ApiError(503, 'SERVICE_UNAVAILABLE', 'down'));
    await flush();
    expect(bad.q.resumeAuth).toBe(0);
    expect(bad.last().error).toEqual({ status: 503, code: 'SERVICE_UNAVAILABLE', retryAfter: null });
    expect(bad.timers).toEqual([]);
  });

  it('(9) conflict → текст R339, request ничего не ставит', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status());
    h.c.onOutcome({ type: 'conflict', text: PAUSE_CONFLICT_TEXT });
    expect(h.last().message).toBe('локальные данные повреждены; переоткройте Mini App');
    expect(await h.c.request(3)).toBe(false);
    expect(await h.c.cancel(5)).toBe(false);
    expect(await h.c.resume(5)).toBe(false);
    expect(h.enq).toEqual([]);
  });

  it('(10) start_at < now → 1 GET сразу + 5 через 2 с, затем стоп', async () => {
    const h = harness();
    h.clock.t = T0 + 1000;
    void h.c.reread();
    await h.answer(status({ pause: pause() }));
    expect(h.gets).toHaveLength(2);
    expect(h.last().polling).toBe(true);
    for (let i = 0; i < 5; i += 1) {
      await h.answer(status({ pause: pause() }));
      expect(h.timers[h.timers.length - 1]?.ms).toBe(PAUSE_START_SERIES_STEP_MS);
      expect(await h.fire()).toBe(true);
    }
    expect(h.gets).toHaveLength(7);
    await h.answer(status({ pause: pause() }));
    expect(await h.fire()).toBe(false);
    expect(h.gets).toHaveLength(7);
    expect(h.last().polling).toBe(false);
  });

  it('(11) start_at = now → серия; start_at > now → серии нет', async () => {
    const eq = harness();
    void eq.c.reread();
    await eq.answer(status({ pause: pause() }));
    expect(eq.gets).toHaveLength(2);

    const fut = harness();
    fut.clock.t = T0 - 1;
    void fut.c.reread();
    await fut.answer(status({ pause: pause() }));
    expect(fut.gets).toHaveLength(1);
    expect(fut.timers).toEqual([]);
    expect(fut.last().polling).toBe(false);
  });

  it('(12) задержка перехода: на 3-м GET состояние активное → серия кончилась, новых GET нет', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status({ pause: pause() }));
    await h.answer(status({ pause: pause() }));
    await h.fire();
    await h.answer(status({ pause: pause({ status: 'active' }), can_request: false, refusal: 'already_open' }));
    expect(h.gets).toHaveLength(3);
    expect(await h.fire()).toBe(false);
    expect(h.last().polling).toBe(false);
  });

  it('(13) повторный apply того же (pause.id, start_at) → вторая серия не стартует; новый start_at → новая серия', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status({ pause: pause() }));
    for (let i = 0; i < 5; i += 1) {
      await h.answer(status({ pause: pause() }));
      await h.fire();
    }
    await h.answer(status({ pause: pause() }));
    expect(h.gets).toHaveLength(7);
    void h.c.reread();
    await h.answer(status({ pause: pause() }));
    expect(h.gets).toHaveLength(8);
    expect(h.last().polling).toBe(false);

    h.clock.t = T0 + 86_400_000;
    void h.c.reread();
    await h.answer(status({ pause: pause({ start_at: new Date(T0 + 86_400_000).toISOString() }) }));
    expect(h.gets).toHaveLength(10);
    expect(h.last().polling).toBe(true);
  });

  it('(14) dispose → запланированное отменено, поздний ответ не применён', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status({ pause: pause() }));
    await h.answer(status({ pause: pause() }));
    void h.c.reread();
    const n = h.views.length;
    h.c.dispose();
    expect(h.timers.every((t) => t.cancelled)).toBe(true);
    expect(h.gets[h.gets.length - 1]?.signal?.aborted).toBe(true);
    await h.answer(status({ start_date: '2027-01-01' }));
    expect(h.views.length).toBe(n);
    expect(h.q.resumeAuth).toBe(2);
  });

  it.each(['old-first', 'new-first'])(
    '(15) исход cancel во время GET серии → старый ответ серии не вытесняет новый reread (%s)',
    async (order) => {
      const h = harness();
      void h.c.reread();
      await h.answer(status({ pause: pause() }));
      await h.c.cancel(5);
      const seriesGet = h.gets.length - 1;
      h.c.onOutcome({ type: 'done', kind: 'cancel', result: { status: 'accepted' } });
      const freshGet = h.gets.length - 1;
      expect(h.gets[seriesGet]?.signal?.aborted).toBe(true);
      const old = status({ pause: pause() });
      const fresh = status({ pause: null, start_date: '2026-12-05' });
      if (order === 'old-first') {
        await h.answer(old, seriesGet);
        await h.answer(fresh, freshGet);
      } else {
        await h.answer(fresh, freshGet);
        await h.answer(old, seriesGet);
      }
      expect(h.last().data?.pause).toBeNull();
      expect(h.last().data?.start_date).toBe('2026-12-05');
      expect(h.last().polling).toBe(false);
      expect(h.last().busy).toBe(false);
    },
  );

  it.each(['old-first', 'new-first'])(
    '(15) исход resume во время GET серии → старый ответ серии не вытесняет новый reread (%s)',
    async (order) => {
      const h = harness();
      void h.c.reread();
      await h.answer(status({ pause: pause() }));
      await h.c.resume(5);
      const seriesGet = h.gets.length - 1;
      h.c.onOutcome({ type: 'business', code: 'PAUSE_NOT_ACTIVE' });
      const freshGet = h.gets.length - 1;
      const old = status({ pause: pause() });
      const fresh = status({ pause: pause({ status: 'active' }), can_request: false, refusal: 'already_open' });
      if (order === 'old-first') {
        await h.answer(old, seriesGet);
        await h.answer(fresh, freshGet);
      } else {
        await h.answer(fresh, freshGet);
        await h.answer(old, seriesGet);
      }
      expect(h.last().data?.pause?.status).toBe('active');
      expect(h.last().polling).toBe(false);
    },
  );

  it('(16) финал серии не сбрасывает busy более нового reread', async () => {
    const h = harness();
    void h.c.reread();
    await h.answer(status({ pause: pause() }));
    for (let i = 0; i < 5; i += 1) {
      await h.answer(status({ pause: pause() }));
      await h.fire();
    }
    const lastSeriesGet = h.gets.length - 1;
    void h.c.reread();
    expect(h.last().loading).toBe(true);
    await h.answer(status({ pause: pause() }), lastSeriesGet);
    expect(h.last().loading).toBe(true);
    await h.answer(status({ pause: pause({ status: 'active' }) }));
    expect(h.last().loading).toBe(false);
    expect(h.last().polling).toBe(false);
  });
});
