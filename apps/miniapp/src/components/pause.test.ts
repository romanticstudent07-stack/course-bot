// apps/miniapp/src/components/pause.test.ts — vitest, environment node, без DOM (miniapp-pause-1 §10).
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
// Асинхронная логика — контроллер pause.ts с подставными вызовами и ручными таймерами.
import { readFileSync } from 'node:fs';

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type PauseInfo, type PauseOverview } from '../api/client.ts';
import { PausedView } from '../pages/PausedPage/PausedPage.tsx';
import {
  CONFLICT_TEXT,
  ERROR_TEXT,
  PAUSE_TEXT,
  POLL_INTERVAL_MS,
  POLL_LIMIT,
  REFUSAL_TEXT,
  REFUSAL_UNKNOWN,
  canMountDay,
  canRequestDays,
  checkDayAccess,
  createPauseController,
  dayGate,
  dayOptions,
  etaText,
  pauseErrorMessage,
  pauseKind,
  pauseViewModel,
  type PauseDeps,
  type PauseSnapshot,
} from './pause.ts';

const NOW = Date.parse('2026-11-21T10:00:00Z');
const H = 3_600_000;

function pause(status: string, over: Partial<PauseInfo> = {}): PauseInfo {
  return {
    id: 7,
    status,
    start_at: new Date(NOW + 14 * H).toISOString(),
    planned_end_at: new Date(NOW + 86 * H).toISOString(),
    ...over,
  };
}

function ov(p: PauseInfo | null, over: Partial<PauseOverview> = {}): PauseOverview {
  return {
    budget_days_left: 14,
    budget_days_total: 14,
    cycle_ends_at: '2027-03-01T00:00:00+03:00',
    pause: p,
    can_request: p === null,
    refusal: p === null ? null : 'already_open',
    ...over,
  };
}

/** Ручные таймеры и часы. */
function clock() {
  let now = NOW;
  let seq = 0;
  const timers = new Map<number, { at: number; fn: () => void }>();
  return {
    now: () => now,
    setTimer: (fn: () => void, ms: number) => {
      seq += 1;
      timers.set(seq, { at: now + ms, fn });
      return seq;
    },
    clearTimer: (h: unknown) => {
      timers.delete(h as number);
    },
    pending: () => timers.size,
    /** Сдвинуть часы и выполнить наступившие таймеры по порядку. */
    async advance(ms: number) {
      const target = now + ms;
      for (;;) {
        const next = [...timers.entries()].filter(([, t]) => t.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
        if (next === undefined) break;
        timers.delete(next[0]);
        now = next[1].at;
        next[1].fn();
        await flush();
      }
      now = target;
    },
  };
}

async function flush() {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

function setup(gets: (() => Promise<unknown>)[], over: Partial<PauseDeps> = {}) {
  const c = clock();
  const queue = [...gets];
  const getPause = vi.fn(() => (queue.shift() ?? (() => Promise.reject(new Error('no more'))))());
  let op = 0;
  const deps: PauseDeps = {
    getPause,
    postPauseRequest: vi.fn(async () => ({ pause: pause('requested') })),
    postPauseCancel: vi.fn(async () => ({ status: 'accepted' })),
    postPauseResume: vi.fn(async () => ({ status: 'accepted' })),
    newOpId: () => `op-${++op}`,
    now: c.now,
    setTimer: c.setTimer,
    clearTimer: c.clearTimer,
    ...over,
  };
  const snaps: PauseSnapshot[] = [];
  const ctrl = createPauseController(deps, (s) => snaps.push(s));
  return { c, deps, ctrl, getPause, snaps, queue };
}

const ok = (v: unknown) => () => Promise.resolve(v);
const fail = (e: unknown) => () => Promise.reject(e);

describe('pauseKind и допуск дня', () => {
  it('null / requested / approved / active / неизвестный status', () => {
    expect(pauseKind(ov(null))).toBe('none');
    expect(pauseKind(ov(pause('requested')))).toBe('requested');
    expect(pauseKind(ov(pause('approved')))).toBe('approved');
    expect(pauseKind(ov(pause('active')))).toBe('active');
    expect(pauseKind(ov(pause('finished')))).toBe('unknown');
    expect(dayGate(ov(null))).toBe('day');
    expect(dayGate(ov(pause('requested')))).toBe('day');
    expect(dayGate(ov(pause('approved')))).toBe('day');
    expect(dayGate(ov(pause('active')))).toBe('paused');
    expect(dayGate(ov(pause('weird')))).toBe('error');
    expect(dayGate({ pause: null })).toBe('error');
    expect(dayGate(null)).toBe('error');
  });

  it('loading / ошибка / active не разрешают монтаж дня; pending / null разрешают', async () => {
    expect(canMountDay('loading')).toBe(false);
    expect(canMountDay('error')).toBe(false);
    expect(canMountDay('paused')).toBe(false);
    expect(canMountDay('day')).toBe(true);
    for (const err of [new ApiError(401, 'TG_INIT_INVALID', ''), new ApiError(503, 'SERVICE_UNAVAILABLE', ''), new TypeError('net')]) {
      expect(await checkDayAccess(fail(err))).toBe('error');
    }
    expect(await checkDayAccess(ok(ov(pause('active'))))).toBe('paused');
    expect(await checkDayAccess(ok(ov(pause('approved'))))).toBe('day');
    expect(await checkDayAccess(ok(ov(null)))).toBe('day');
  });
});

describe('бюджет, can_request и причины', () => {
  it('дни 1..min(7, left); can_request и открытая пауза ограничивают', () => {
    expect(dayOptions(ov(null))).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(dayOptions(ov(null, { budget_days_left: 3 }))).toEqual([1, 2, 3]);
    expect(dayOptions(ov(null, { budget_days_left: 0 }))).toEqual([]);
    expect(canRequestDays(ov(null), 7)).toBe(true);
    expect(canRequestDays(ov(null), 8)).toBe(false);
    expect(canRequestDays(ov(null), 0)).toBe(false);
    expect(canRequestDays(ov(null), 1.5)).toBe(false);
    expect(canRequestDays(ov(null, { budget_days_left: 3 }), 4)).toBe(false);
    expect(canRequestDays(ov(null, { can_request: false, refusal: 'gap_24h' }), 1)).toBe(false);
    expect(canRequestDays(ov(pause('requested')), 1)).toBe(false);
  });

  it('причины отказов — заглушки; неизвестная — нейтральная; не «сгорание»', () => {
    for (const reason of Object.keys(REFUSAL_TEXT)) {
      const s = { ...stateReady(ov(null, { can_request: false, refusal: reason })) };
      expect(pauseViewModel(s, s.overview as PauseOverview).refusal).toBe(REFUSAL_TEXT[reason as keyof typeof REFUSAL_TEXT]);
    }
    const s = stateReady(ov(null, { can_request: false, refusal: 'mystery' }));
    expect(pauseViewModel(s, s.overview as PauseOverview).refusal).toBe(REFUSAL_UNKNOWN);
    const e = new ApiError(409, 'PAUSE_REFUSED', 'server text', null, { reason: 'stage_taken' });
    expect(pauseErrorMessage(e)).toBe(REFUSAL_TEXT.stage_taken);
    expect(pauseErrorMessage(new ApiError(409, 'PAUSE_REFUSED', 'x', null, { reason: 42 }))).toBe(REFUSAL_UNKNOWN);
    expect(pauseErrorMessage(new ApiError(409, 'PAUSE_REFUSED', 'x', null, 'junk'))).toBe(REFUSAL_UNKNOWN);
    for (const v of Object.values(REFUSAL_TEXT)) expect(v.toLowerCase()).not.toContain('сгор');
  });

  it('только тексты-заглушки', () => {
    const all = [
      ...Object.values(PAUSE_TEXT),
      ...Object.values(REFUSAL_TEXT),
      ...Object.values(CONFLICT_TEXT),
      ...Object.values(ERROR_TEXT),
      REFUSAL_UNKNOWN,
    ];
    for (const v of all) expect(v.startsWith('Заглушка: ')).toBe(true);
  });
});

function stateReady(o: PauseOverview, over: Partial<PauseSnapshot> = {}): PauseSnapshot {
  return {
    load: 'ready',
    overview: o,
    loadError: null,
    actionError: null,
    busy: false,
    attempt: null,
    days: 1,
    polling: false,
    rateLimitedUntil: null,
    now: NOW,
    ...over,
  };
}

describe('запрос паузы', () => {
  it('201 не active: статус — только из GET; двойной клик — один POST', async () => {
    const { ctrl, deps, getPause } = setup([ok(ov(null)), ok(ov(pause('requested')))]);
    ctrl.start();
    await flush();
    ctrl.setDays(3);
    const p1 = ctrl.request();
    const p2 = ctrl.request();
    await Promise.all([p1, p2]);
    await flush();
    expect(deps.postPauseRequest).toHaveBeenCalledTimes(1);
    expect(deps.postPauseRequest).toHaveBeenCalledWith(3, 'op-1');
    expect(getPause).toHaveBeenCalledTimes(2);
    expect(pauseKind(ctrl.snapshot().overview as PauseOverview)).toBe('requested');
    expect(ctrl.snapshot().busy).toBe(false);
  });

  it('неопределённый исход (сеть / 503): та же пара {days, op-id}, days не меняются, без автоповтора', async () => {
    const post = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('net'))
      .mockRejectedValueOnce(new ApiError(503, 'SERVICE_UNAVAILABLE', ''))
      .mockResolvedValueOnce({ pause: pause('requested') });
    const { ctrl, getPause } = setup([ok(ov(null)), ok(ov(pause('requested')))], { postPauseRequest: post });
    ctrl.start();
    await flush();
    ctrl.setDays(5);
    await ctrl.request();
    expect(post).toHaveBeenCalledTimes(1);
    expect(ctrl.snapshot().attempt).toEqual({ days: 5, opId: 'op-1' });
    ctrl.setDays(2);
    expect(ctrl.snapshot().days).toBe(5);
    await ctrl.request();
    await ctrl.request();
    expect(post.mock.calls).toEqual([[5, 'op-1'], [5, 'op-1'], [5, 'op-1']]);
    expect(ctrl.snapshot().attempt).toBeNull();
    expect(getPause).toHaveBeenCalledTimes(2);
  });

  it('успешный GET с открытой паузой снимает повтор request', async () => {
    const { ctrl, c } = setup([ok(ov(null)), ok(ov(pause('requested')))], {
      postPauseRequest: vi.fn().mockRejectedValue(new TypeError('net')),
    });
    ctrl.start();
    await flush();
    await ctrl.request();
    expect(ctrl.snapshot().attempt).not.toBeNull();
    ctrl.refresh();
    await flush();
    expect(ctrl.snapshot().attempt).toBeNull();
    ctrl.dispose();
    expect(c.pending()).toBe(0);
  });

  it('409: заглушка по коду и перечитывание GET; ошибки 401/404/422 — без повтора POST', async () => {
    const post = vi.fn().mockRejectedValue(new ApiError(409, 'PAUSE_ALREADY_OPEN', 'srv'));
    const { ctrl, getPause } = setup([ok(ov(null)), ok(ov(pause('approved')))], { postPauseRequest: post });
    ctrl.start();
    await flush();
    await ctrl.request();
    expect(getPause).toHaveBeenCalledTimes(2);
    expect(pauseErrorMessage(ctrl.snapshot().actionError)).toBe(CONFLICT_TEXT.PAUSE_ALREADY_OPEN);
    expect(ctrl.snapshot().attempt).toBeNull();

    for (const [status, code, text] of [
      [401, 'TG_INIT_INVALID', ERROR_TEXT.unauthorized],
      [404, 'PARTICIPANT_NOT_FOUND', ERROR_TEXT.notFound],
      [422, 'VALIDATION_ERROR', ERROR_TEXT.validation],
    ] as const) {
      const p = vi.fn().mockRejectedValue(new ApiError(status, code, 'srv'));
      const t = setup([ok(ov(null))], { postPauseRequest: p });
      t.ctrl.start();
      await flush();
      await t.ctrl.request();
      await t.c.advance(60_000);
      expect(p).toHaveBeenCalledTimes(1);
      expect(t.getPause).toHaveBeenCalledTimes(1);
      expect(pauseErrorMessage(t.ctrl.snapshot().actionError)).toBe(text);
      expect(t.ctrl.snapshot().attempt).toBeNull();
    }
    expect(pauseErrorMessage(new ApiError(503, 'SERVICE_UNAVAILABLE', 'srv'))).toBe(ERROR_TEXT.unavailable);
    expect(pauseErrorMessage(new TypeError('Failed to fetch'))).toBe(ERROR_TEXT.network);
  });
});

describe('отмена и продолжение', () => {
  it('202 + старый GET — не завершение; до 5 повторов через 2 с; затем вручную', async () => {
    const same = ok(ov(pause('approved')));
    const { ctrl, c, getPause, deps } = setup([same, ...Array.from({ length: 10 }, () => same)]);
    ctrl.start();
    await flush();
    const p1 = ctrl.cancel();
    void ctrl.cancel();
    await p1;
    await flush();
    expect(deps.postPauseCancel).toHaveBeenCalledTimes(1);
    expect(getPause).toHaveBeenCalledTimes(2);
    expect(ctrl.snapshot().busy).toBe(true);
    await c.advance(POLL_INTERVAL_MS * (POLL_LIMIT + 3));
    expect(getPause).toHaveBeenCalledTimes(2 + POLL_LIMIT);
    expect(ctrl.snapshot().busy).toBe(false);
    expect(ctrl.snapshot().polling).toBe(false);
    ctrl.dispose();
    expect(c.pending()).toBe(0);
  });

  it('последующий null завершает повторы; день снова доступен через проверку', async () => {
    const { ctrl, c, getPause } = setup([ok(ov(pause('active'))), ok(ov(pause('active'))), ok(ov(null))]);
    ctrl.start();
    await flush();
    await ctrl.resume();
    await flush();
    await c.advance(POLL_INTERVAL_MS);
    expect(getPause).toHaveBeenCalledTimes(3);
    expect(pauseKind(ctrl.snapshot().overview as PauseOverview)).toBe('none');
    expect(ctrl.snapshot().busy).toBe(false);
    await c.advance(POLL_INTERVAL_MS * 10);
    expect(getPause).toHaveBeenCalledTimes(3);
    const vm = pauseViewModel(ctrl.snapshot(), ctrl.snapshot().overview as PauseOverview);
    expect(vm.showToDay).toBe(true);
    ctrl.dispose();
  });

  it('409 PAUSE_NOT_CANCELLABLE → заглушка и перечитывание', async () => {
    const { ctrl, getPause } = setup([ok(ov(pause('requested'))), ok(ov(pause('active')))], {
      postPauseCancel: vi.fn().mockRejectedValue(new ApiError(409, 'PAUSE_NOT_CANCELLABLE', 'srv')),
    });
    ctrl.start();
    await flush();
    await ctrl.cancel();
    expect(getPause).toHaveBeenCalledTimes(2);
    expect(pauseErrorMessage(ctrl.snapshot().actionError)).toBe(CONFLICT_TEXT.PAUSE_NOT_CANCELLABLE);
    ctrl.dispose();
  });
});

describe('таймеры, устаревшие ответы, 429', () => {
  it('GET на start_at, затем до 5 повторов при прежнем статусе; день таймер не разрешает', async () => {
    const same = ok(ov(pause('approved')));
    const { ctrl, c, getPause } = setup(Array.from({ length: 12 }, () => same));
    ctrl.start();
    await flush();
    await c.advance(14 * H - 1);
    expect(getPause).toHaveBeenCalledTimes(1);
    await c.advance(1);
    expect(getPause).toHaveBeenCalledTimes(2);
    await c.advance(POLL_INTERVAL_MS * 20);
    expect(getPause).toHaveBeenCalledTimes(2 + POLL_LIMIT);
    expect(dayGate(ctrl.snapshot().overview)).toBe('day');
    ctrl.dispose();
    expect(c.pending()).toBe(0);
  });

  it('ETA: истечение вызывает GET, но статус не меняет и день не открывает', async () => {
    const active = ov(pause('active', { start_at: new Date(NOW - H).toISOString(), planned_end_at: new Date(NOW + 2 * H).toISOString() }));
    const { ctrl, c, getPause } = setup([ok(active), ok(active)]);
    ctrl.start();
    await flush();
    expect(etaText(active.pause!.planned_end_at, NOW)).toBe(`${PAUSE_TEXT.etaPrefix}: 0 д 2 ч 0 мин`);
    await c.advance(2 * H);
    expect(getPause).toHaveBeenCalledTimes(2);
    expect(pauseKind(ctrl.snapshot().overview as PauseOverview)).toBe('active');
    expect(dayGate(ctrl.snapshot().overview)).toBe('paused');
    expect(etaText(active.pause!.planned_end_at, c.now())).toBe(PAUSE_TEXT.etaOver);
    ctrl.dispose();
    expect(c.pending()).toBe(0);
  });

  it('устаревший ответ игнорируется; ответ после dispose не применяется', async () => {
    let resolveOld: (v: unknown) => void = () => undefined;
    const old = () => new Promise((r) => { resolveOld = r; });
    const { ctrl, snaps } = setup([old, ok(ov(null))]);
    ctrl.start();
    ctrl.refresh();
    await flush();
    expect(pauseKind(ctrl.snapshot().overview as PauseOverview)).toBe('none');
    resolveOld(ov(pause('active')));
    await flush();
    expect(pauseKind(ctrl.snapshot().overview as PauseOverview)).toBe('none');

    let resolveLate: (v: unknown) => void = () => undefined;
    const t = setup([() => new Promise((r) => { resolveLate = r; })]);
    t.ctrl.start();
    t.ctrl.dispose();
    const count = t.snaps.length;
    resolveLate(ov(null));
    await flush();
    expect(t.snaps.length).toBe(count);
    expect(snaps.length).toBeGreaterThan(0);
  });

  it('429 с Retry-After: нет фоновых GET и повтора запроса до истечения; затем — вручную', async () => {
    const rate = new ApiError(429, 'RATE_LIMITED', '', 10);
    const same = ok(ov(pause('approved')));
    const { ctrl, c, getPause } = setup([same, same, fail(rate), same]);
    ctrl.start();
    await flush();
    await ctrl.cancel();
    await flush();
    await c.advance(POLL_INTERVAL_MS);
    expect(getPause).toHaveBeenCalledTimes(3);
    expect(ctrl.snapshot().rateLimitedUntil).toBe(c.now() + 10_000);
    expect(pauseErrorMessage(ctrl.snapshot().loadError)).toBe(ERROR_TEXT.rateLimited);
    ctrl.refresh();
    await c.advance(9_000);
    expect(getPause).toHaveBeenCalledTimes(3);
    await c.advance(1_000);
    expect(ctrl.snapshot().rateLimitedUntil).toBeNull();
    expect(getPause).toHaveBeenCalledTimes(3);
    ctrl.refresh();
    await flush();
    expect(getPause).toHaveBeenCalledTimes(4);
    ctrl.dispose();
  });

  it('429 на request: кнопка запроса отключена до Retry-After', async () => {
    const post = vi.fn().mockRejectedValue(new ApiError(429, 'RATE_LIMITED', '', 30));
    const { ctrl, c } = setup([ok(ov(null))], { postPauseRequest: post });
    ctrl.start();
    await flush();
    await ctrl.request();
    const s = ctrl.snapshot();
    expect(pauseViewModel(s, s.overview as PauseOverview).requestEnabled).toBe(false);
    await ctrl.request();
    expect(post).toHaveBeenCalledTimes(1);
    await c.advance(30_000);
    const s2 = ctrl.snapshot();
    expect(pauseViewModel(s2, s2.overview as PauseOverview).requestEnabled).toBe(true);
    ctrl.dispose();
  });
});

function render(s: PauseSnapshot): string {
  const noop = () => undefined;
  return renderToStaticMarkup(
    createElement(PausedView, {
      vm: pauseViewModel(s, s.overview as PauseOverview),
      onDays: noop,
      onRequest: noop,
      onCancel: noop,
      onResume: noop,
      onRefresh: noop,
    }),
  );
}

describe('PausedView: статический рендер', () => {
  it('кнопки по статусам, бюджет, границы, три полосы и ETA', () => {
    const none = render(stateReady(ov(null, { budget_days_left: 9 })));
    expect(none).toContain(`${PAUSE_TEXT.budget}: 9 / 14`);
    expect(none).toContain(PAUSE_TEXT.request);
    expect(none).toContain(PAUSE_TEXT.statusNone);
    expect(none).not.toContain(PAUSE_TEXT.cancel);
    expect(none).not.toContain(PAUSE_TEXT.resume);

    for (const status of ['requested', 'approved'] as const) {
      const html = render(stateReady(ov(pause(status))));
      expect(html).toContain(PAUSE_TEXT.cancel);
      expect(html).not.toContain(PAUSE_TEXT.request);
      expect(html).not.toContain(PAUSE_TEXT.resume);
      expect(html).toContain(PAUSE_TEXT.startsAt);
    }
    expect(render(stateReady(ov(pause('requested'))))).toContain(PAUSE_TEXT.statusRequested);
    expect(render(stateReady(ov(pause('approved'))))).toContain(PAUSE_TEXT.statusApproved);

    const active = render(stateReady(ov(pause('active', { start_at: new Date(NOW - H).toISOString() }))));
    expect(active).toContain(PAUSE_TEXT.resume);
    expect(active).not.toContain(PAUSE_TEXT.cancel);
    expect(active.match(/<progress/g)).toHaveLength(3);
    expect(active).toContain(PAUSE_TEXT.etaPrefix);

    const unknown = render(stateReady(ov(pause('weird'))));
    expect(unknown).toContain(PAUSE_TEXT.statusUnknown);
    expect(unknown).not.toContain(PAUSE_TEXT.cancel);
    expect(unknown).not.toContain(PAUSE_TEXT.resume);
  });

  it('отказ сервера: запрос отключён, причина-заглушка; занятость отключает действия', () => {
    const html = render(stateReady(ov(null, { can_request: false, refusal: 'no_budget' })));
    expect(html).toContain(REFUSAL_TEXT.no_budget);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Заглушка: запросить паузу/);
    const busy = render(stateReady(ov(pause('active')), { busy: true }));
    expect(busy).toMatch(/<button[^>]*disabled=""[^>]*>Заглушка: продолжить курс/);
  });
});

describe('статически: маршрут /paused и проверка в App', () => {
  const src = (p: string) => readFileSync(new URL(p, import.meta.url), 'utf8');

  it('routes.tsx содержит /paused и не содержит /returned', () => {
    const routes = src('../navigation/routes.tsx');
    expect(routes).toContain("{ path: '/paused', Component: PausedPage }");
    expect(routes).not.toContain("'/returned'");
  });

  it('App.tsx: /day — только через DayGuard; фазы и /help без изменений', () => {
    const app = src('./App.tsx');
    expect(app).toContain("import { DayGuard } from '@/pages/PausedPage/PausedPage.tsx';");
    expect(app).toContain('<DayGuard><Component/></DayGuard>');
    expect(app).toContain(
      "type Phase = 'checking' | 'start-error' | 'no-access' | 'number' | 'onboarding' | 'later' | 'app';",
    );
    expect(app).toContain('<Route path="/help"');
    expect(app).toContain('<Route path="*" element={<Navigate to="/day"/>}/>');
    expect(app).toContain('<HelpBar/>');
  });
});
