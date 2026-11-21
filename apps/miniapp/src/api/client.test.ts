import { describe, expect, it } from 'vitest';

import { buildUrl, normalizeBaseUrl } from './client.ts';

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
