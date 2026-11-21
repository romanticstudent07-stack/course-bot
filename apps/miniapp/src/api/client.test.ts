import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  buildUrl,
  getPause,
  normalizeBaseUrl,
  postPauseCancel,
  postPauseRequest,
  postPauseResume,
} from './client.ts';

describe('normalizeBaseUrl', () => {
  it('пустое значение → тот же origin', () => {
    expect(normalizeBaseUrl(undefined)).toBe('');
    expect(normalizeBaseUrl('  ')).toBe('');
  });

  it('срезает завершающие слэши', () => {
    expect(normalizeBaseUrl('https://example.test///')).toBe('https://example.test');
  });
});

describe('buildUrl', () => {
  it('относительный путь при пустом base', () => {
    expect(buildUrl('', '/miniapp/v1/onboarding/first-launch')).toBe(
      '/miniapp/v1/onboarding/first-launch',
    );
  });

  it('добавляет ведущий слэш', () => {
    expect(buildUrl('https://example.test/', 'healthz')).toBe('https://example.test/healthz');
  });
});

// ---- Пауза (miniapp-pause-1 §10) ----
const UUID4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn(async (_url: string, _init: RequestInit) =>
    new Response(JSON.stringify(body), { status, headers }),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('вызовы паузы', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('точные адреса и методы; UUID4 и тело только у request; cancel/resume без тела', async () => {
    const op = '0b8f7c1e-1d2a-4e3b-9c4d-5e6f7a8b9c0d';
    const cases: [() => Promise<unknown>, string, string, unknown, string | undefined][] = [
      [() => getPause(), '/miniapp/v1/pause', 'GET', undefined, undefined],
      [() => postPauseRequest(3, op), '/miniapp/v1/pause/request', 'POST', JSON.stringify({ days: 3 }), op],
      [() => postPauseCancel(), '/miniapp/v1/pause/cancel', 'POST', undefined, undefined],
      [() => postPauseResume(), '/miniapp/v1/pause/resume', 'POST', undefined, undefined],
    ];
    for (const [call, url, method, body, opId] of cases) {
      const fn = mockFetch(200, {});
      await call();
      const [gotUrl, init] = fn.mock.calls[0];
      const headers = init.headers as Record<string, string>;
      expect(gotUrl).toBe(url);
      expect(init.method).toBe(method);
      expect(init.body).toBe(body);
      expect(headers['X-Client-Op-Id']).toBe(opId);
      if (opId !== undefined) expect(opId).toMatch(UUID4_RE);
      expect('Content-Type' in headers).toBe(body !== undefined);
    }
  });

  it('409: details.reason — аргумент 5; retryAfter (аргумент 4) — null', async () => {
    mockFetch(409, { code: 'PAUSE_REFUSED', message: 'x', details: { reason: 'gap_24h' } });
    const err = await postPauseRequest(1, 'op').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect([e.status, e.code, e.retryAfter]).toEqual([409, 'PAUSE_REFUSED', null]);
    expect(e.details).toEqual({ reason: 'gap_24h' });
    expect(new ApiError(429, 'RATE_LIMITED', '', 5, { reason: 'r' }).retryAfter).toBe(5);
    expect(new ApiError(429, 'RATE_LIMITED', '', 5).details).toBeUndefined();
  });

  it('429: Retry-After в аргументе 4', async () => {
    mockFetch(429, { code: 'RATE_LIMITED', message: 'x' }, { 'Retry-After': '7' });
    const e = (await getPause().catch((x: unknown) => x)) as ApiError;
    expect(e.retryAfter).toBe(7);
    expect(e.details).toBeUndefined();
  });
});
