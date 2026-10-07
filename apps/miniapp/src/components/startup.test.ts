// apps/miniapp/src/components/startup.test.ts — vitest, environment node.
// Старт Mini App (returning-2): номер только при returning с short_no; всё остальное —
// онбординг; после номера — анкета или курс; тексты ошибок status.
import { describe, expect, it } from 'vitest';

import { ApiError } from '../api/client.ts';
import type { Draft } from './drafts.ts';
import { afterNumber, isReconsent, returningShortNo, startErrorMessage, startPhase } from './startup.ts';

describe('startPhase', () => {
  it('returning с short_no → number', () => {
    const resp = { status: 'returning', short_no: '#000001' };
    expect(startPhase(resp)).toBe('number');
    expect(returningShortNo(resp)).toBe('#000001');
  });

  it('returning без short_no / с пустым → onboarding', () => {
    const bad: unknown[] = [
      { status: 'returning' },
      { status: 'returning', short_no: '' },
      { status: 'returning', short_no: '   ' },
      { status: 'returning', short_no: 1 },
      { status: 'returning', short_no: null },
    ];
    for (const resp of bad) {
      expect(startPhase(resp)).toBe('onboarding');
      expect(returningShortNo(resp)).toBeNull();
    }
  });

  it('reconsent → onboarding', () => {
    expect(startPhase({ status: 'reconsent', reasons: ['C1'] })).toBe('onboarding');
  });

  it('new → onboarding', () => {
    expect(startPhase({ status: 'new' })).toBe('onboarding');
  });

  it('неизвестный status и битое тело → onboarding', () => {
    const bad: unknown[] = [{ status: 'x' }, {}, [], null, undefined, 'returning', 42];
    for (const resp of bad) expect(startPhase(resp)).toBe('onboarding');
  });
});

describe('isReconsent', () => {
  it('только status reconsent', () => {
    expect(isReconsent({ status: 'reconsent', reasons: [] })).toBe(true);
    expect(isReconsent({ status: 'new' })).toBe(false);
    expect(isReconsent({ status: 'returning', short_no: '#000001' })).toBe(false);
    expect(isReconsent(null)).toBe(false);
    expect(isReconsent('reconsent')).toBe(false);
  });
});

describe('afterNumber', () => {
  const draft = (step: Draft['step']): Draft => ({ step, email: '', city: '' });

  it('черновика нет → app', () => {
    expect(afterNumber(null)).toBe('app');
  });

  it('step finished → app', () => {
    expect(afterNumber(draft('finished'))).toBe('app');
  });

  it('незаконченный шаг → later', () => {
    expect(afterNumber(draft('email'))).toBe('later');
    expect(afterNumber(draft('offer'))).toBe('later');
  });
});

describe('startErrorMessage', () => {
  it('401 → текст про вход через Telegram', () => {
    expect(startErrorMessage(new ApiError(401, 'TG_INIT_INVALID', 'x'))).toBe(
      'Не удалось подтвердить вход через Telegram. Нажмите «Повторить» или откройте приложение заново.',
    );
  });

  it('429', () => {
    expect(startErrorMessage(new ApiError(429, 'RATE_LIMITED', 'x'))).toBe(
      'Слишком много попыток подряд. Подождите минуту и нажмите «Повторить».',
    );
  });

  it('503', () => {
    expect(startErrorMessage(new ApiError(503, 'SERVICE_UNAVAILABLE', 'x'))).toBe(
      'Сервис временно недоступен. Попробуйте чуть позже.',
    );
  });

  it('прочая ошибка API', () => {
    expect(startErrorMessage(new ApiError(500, 'HTTP_ERROR', 'x'))).toBe('Что-то пошло не так. Нажмите «Повторить».');
  });

  it('сеть (TypeError) → текст про интернет', () => {
    expect(startErrorMessage(new TypeError('Failed to fetch'))).toBe(
      'Не удалось связаться с сервером. Проверьте интернет и нажмите «Повторить».',
    );
  });
});
