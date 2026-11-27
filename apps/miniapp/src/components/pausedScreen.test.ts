// apps/miniapp/src/components/pausedScreen.test.ts — vitest, environment node, без DOM (miniapp-pause-c3b §9, c3b-1).
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
// Исходники DayGuard.tsx и pausedScreen.ts проверяются поиском по тексту.
// Пункт «PausedPage.tsx: нет setInterval» — в c3b-2 вместе с экраном.
import { readFileSync } from 'node:fs';

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { PauseOut, PauseStatus } from '../api/client.ts';
import { DAY_GUARD_PAUSED_TEXT, DayGuard, DayGuardErrorView } from './DayGuard.tsx';
import { PAUSE_CONFLICT_TEXT, PAUSE_STATUS_CANCELLABLE, type PauseView } from './pause.ts';
import {
  PAUSED_TEXT,
  REFUSAL_FALLBACK_TEXT,
  REFUSAL_TEXTS,
  formatEta,
  pauseBars,
  pausedView,
  refusalText,
} from './pausedScreen.ts';

const NOW = Date.parse('2026-11-27T12:00:00Z');
const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const BUTTON_DISABLED_RE = /<button[^>]*\sdisabled=""/;
const noop = () => undefined;

function iso(ms: number): string {
  return new Date(ms).toISOString();
}

function pauseOut(status: string, startMs: number, endMs: number): PauseOut {
  return { id: 7, status, start_at: iso(startMs), planned_end_at: iso(endMs) };
}

function pauseStatus(over: Partial<PauseStatus> = {}): PauseStatus {
  return {
    budget_days_left: 10,
    budget_days_total: 14,
    cycle_ends_at: null,
    pause: null,
    can_request: true,
    refusal: null,
    start_date: '2026-11-28',
    ...over,
  };
}

function snap(data: PauseStatus | null, over: Partial<PauseView> = {}): PauseView {
  return {
    data,
    loading: false,
    error: null,
    message: null,
    busy: false,
    polling: false,
    confirmStart: false,
    closed: false,
    ...over,
  };
}

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8');
}

describe('pausedView: кнопки по статусу', () => {
  it('active → resume, две полосы и ETA', () => {
    const data = pauseStatus({
      can_request: false,
      refusal: 'already_open',
      pause: pauseOut('active', NOW - DAY, NOW + 2 * DAY + 5 * HOUR),
    });
    const v = pausedView(snap(data), NOW);
    expect(v.kind).toBe('active');
    expect(v.buttons).toEqual(['resume']);
    expect(v.bars).toEqual([
      { id: 'budget', label: PAUSED_TEXT.budgetBar, percent: 71 },
      { id: 'progress', label: PAUSED_TEXT.progressBar, percent: 31 },
    ]);
    expect(v.eta).toBe('До конца паузы: 2 дн. 5 ч');
  });

  it('requested и approved → cancel, без ETA и без «Хода паузы»', () => {
    expect([...PAUSE_STATUS_CANCELLABLE]).toEqual(['requested', 'approved']);
    for (const status of PAUSE_STATUS_CANCELLABLE) {
      const data = pauseStatus({
        can_request: false,
        refusal: 'already_open',
        pause: pauseOut(status, NOW + DAY, NOW + 4 * DAY),
      });
      const v = pausedView(snap(data), NOW);
      expect(v.kind).toBe('cancellable');
      expect(v.buttons).toEqual(['cancel']);
      expect(v.eta).toBeNull();
      expect(v.bars.map((b) => b.id)).toEqual(['budget']);
    }
  });

  it('pause null и can_request → форма запроса', () => {
    const v = pausedView(snap(pauseStatus()), NOW);
    expect(v.kind).toBe('request');
    expect(v.buttons).toEqual(['request']);
    expect(v.eta).toBeNull();
  });

  it('pause null и !can_request → текст отказа, без кнопок', () => {
    const known = pausedView(snap(pauseStatus({ can_request: false, refusal: 'already_open' })), NOW);
    expect(known.kind).toBe('refused');
    expect(known.buttons).toEqual([]);
    expect(known.message).toBe(REFUSAL_TEXTS.already_open);
    const unknown = pausedView(snap(pauseStatus({ can_request: false, refusal: 'something_new' })), NOW);
    expect(unknown.message).toBe(REFUSAL_FALLBACK_TEXT);
  });

  it('другой статус → без кнопок', () => {
    const data = pauseStatus({ can_request: false, pause: pauseOut('finished', NOW - 3 * DAY, NOW - DAY) });
    const v = pausedView(snap(data), NOW);
    expect(v.kind).toBe('other');
    expect(v.buttons).toEqual([]);
  });

  it('коллизия (closed) → текст R339, кнопок нет даже при active', () => {
    const data = pauseStatus({ pause: pauseOut('active', NOW - DAY, NOW + DAY) });
    const v = pausedView(snap(data, { closed: true }), NOW);
    expect(v.kind).toBe('closed');
    expect(v.buttons).toEqual([]);
    expect(v.message).toBe(PAUSE_CONFLICT_TEXT);
  });

  it('данных нет → loading или error, без кнопок', () => {
    expect(pausedView(snap(null, { loading: true }), NOW).kind).toBe('loading');
    const err = pausedView(snap(null, { error: { status: 503, code: 'SERVICE_UNAVAILABLE', retryAfter: null } }), NOW);
    expect(err.kind).toBe('error');
    expect(err.buttons).toEqual([]);
  });

  it('сообщение операции из снимка сохраняется', () => {
    const v = pausedView(snap(pauseStatus(), { message: 'msg' }), NOW);
    expect(v.message).toBe('msg');
  });
});

describe('formatEta', () => {
  it('дни и часы', () => {
    expect(formatEta(iso(NOW + 2 * DAY + 5 * HOUR), NOW)).toBe('До конца паузы: 2 дн. 5 ч');
    expect(formatEta(iso(NOW + 3 * HOUR), NOW)).toBe('До конца паузы: 0 дн. 3 ч');
    expect(formatEta(iso(NOW + 30 * 60_000), NOW)).toBe('До конца паузы: 0 дн. 1 ч');
  });

  it('срок прошёл → «Пауза завершается»', () => {
    expect(formatEta(iso(NOW), NOW)).toBe(PAUSED_TEXT.etaEnding);
    expect(formatEta(iso(NOW - HOUR), NOW)).toBe('Пауза завершается');
  });

  it('битая дата → null', () => {
    expect(formatEta('not-a-date', NOW)).toBeNull();
  });
});

describe('pauseBars', () => {
  it('total 0 → полосы бюджета нет', () => {
    expect(pauseBars(pauseStatus({ budget_days_left: 0, budget_days_total: 0 }), NOW)).toEqual([]);
  });

  it('бюджет: доля left / total, обрезка до 100', () => {
    expect(pauseBars(pauseStatus({ budget_days_left: 7, budget_days_total: 14 }), NOW)).toEqual([
      { id: 'budget', label: PAUSED_TEXT.budgetBar, percent: 50 },
    ]);
    expect(pauseBars(pauseStatus({ budget_days_left: 20, budget_days_total: 14 }), NOW)[0]?.percent).toBe(100);
  });

  it('«Ход паузы»: обрезка 0..100', () => {
    const progress = (startMs: number, endMs: number) =>
      pauseBars(pauseStatus({ pause: pauseOut('active', startMs, endMs) }), NOW).find((b) => b.id === 'progress')
        ?.percent;
    expect(progress(NOW + HOUR, NOW + DAY)).toBe(0);
    expect(progress(NOW - 2 * DAY, NOW - DAY)).toBe(100);
    expect(progress(NOW - DAY, NOW + DAY)).toBe(50);
  });

  it('«Ход паузы» — только при active', () => {
    const bars = pauseBars(pauseStatus({ pause: pauseOut('requested', NOW - DAY, NOW + DAY) }), NOW);
    expect(bars.map((b) => b.id)).toEqual(['budget']);
  });
});

describe('refusalText', () => {
  it('известный код, неизвестный и null', () => {
    expect(refusalText('already_open')).toBe(REFUSAL_TEXTS.already_open);
    expect(refusalText('other_code')).toBe(REFUSAL_FALLBACK_TEXT);
    expect(refusalText(null)).toBe(REFUSAL_FALLBACK_TEXT);
  });
});

describe('DayGuardErrorView', () => {
  it('retryEnabled false → кнопка disabled', () => {
    const html = renderToStaticMarkup(createElement(DayGuardErrorView, { text: 'err', retryEnabled: false, onRetry: noop }));
    expect(html).toMatch(BUTTON_DISABLED_RE);
    expect(html).toContain('err');
  });

  it('retryEnabled true → без disabled', () => {
    const html = renderToStaticMarkup(createElement(DayGuardErrorView, { text: 'err', retryEnabled: true, onRetry: noop }));
    expect(html).not.toMatch(BUTTON_DISABLED_RE);
  });
});

describe('DayGuard: до ответа GET день не открыт', () => {
  it('первый рендер — «Загрузка…», без children', () => {
    const html = renderToStaticMarkup(createElement(DayGuard, { children: createElement('p', null, 'день открыт') }));
    expect(html).toContain('Загрузка…');
    expect(html).not.toContain('день открыт');
    expect(html).not.toContain(DAY_GUARD_PAUSED_TEXT);
  });
});

describe('исходники: таймеры', () => {
  const guard = source('./DayGuard.tsx');

  it('DayGuard.tsx: нет setInterval', () => {
    expect(guard.toLowerCase()).not.toContain('setinterval');
  });

  it('DayGuard.tsx: единственный setTimeout только включает кнопку и getPause не вызывает', () => {
    const parts = guard.split('setTimeout(');
    expect(parts.length).toBe(2);
    const rest = parts[1] ?? '';
    const call = rest.slice(0, rest.indexOf(');'));
    expect(call).toContain('setRetryEnabled(true)');
    expect(call).not.toContain('getPause');
    expect(call).not.toContain('check');
  });

  it('DayGuard.tsx: повтор с отсрочкой экрана дня не используется (§7.2)', () => {
    expect(guard).not.toContain('dayRetryDelayMs');
  });

  it('pausedScreen.ts: без часов и таймеров, nowMs — аргументом', () => {
    const text = source('./pausedScreen.ts').toLowerCase();
    for (const banned of ['date.now', 'settimeout', 'setinterval']) {
      expect(text.includes(banned), banned).toBe(false);
    }
  });
});
