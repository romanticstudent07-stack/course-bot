// apps/miniapp/src/components/startup.test.ts — vitest, environment node.
// Старт Mini App (returning-2): номер только при returning с short_no; всё остальное —
// онбординг; после номера — анкета или курс; тексты ошибок status.
import { describe, expect, it } from 'vitest';

import { ApiError } from '../api/client.ts';
import type { Draft } from './drafts.ts';
import {
  NO_ACCESS_BUTTON,
  NO_ACCESS_TEXT,
  afterNumber,
  isAccessNotGranted,
  isNoAccess,
  isReconsent,
  returningShortNo,
  startErrorMessage,
  startPhase,
} from './startup.ts';

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
    expect(isReconsent({ status: 'no_access' })).toBe(false);
  });
});

describe('no_access (Р-2)', () => {
  it('startPhase no_access → no-access, номера нет', () => {
    expect(startPhase({ status: 'no_access' })).toBe('no-access');
    expect(returningShortNo({ status: 'no_access' })).toBeNull();
  });

  it('no_access с short_no → no-access (номер не показывается)', () => {
    const resp = { status: 'no_access', short_no: '#000001' };
    expect(startPhase(resp)).toBe('no-access');
    expect(returningShortNo(resp)).toBeNull();
  });

  it('isNoAccess — только объект со status no_access', () => {
    expect(isNoAccess({ status: 'no_access' })).toBe(true);
    expect(isNoAccess({ status: 'new' })).toBe(false);
    expect(isNoAccess({ status: 'returning', short_no: '#000001' })).toBe(false);
    expect(isNoAccess(null)).toBe(false);
    expect(isNoAccess('no_access')).toBe(false);
    expect(isNoAccess([])).toBe(false);
  });

  it('isAccessNotGranted — только ApiError 403 ACCESS_NOT_GRANTED', () => {
    expect(isAccessNotGranted(new ApiError(403, 'ACCESS_NOT_GRANTED', 'x'))).toBe(true);
    expect(isAccessNotGranted(new ApiError(403, 'AGE_GATE_UNDERAGE', 'x'))).toBe(false);
    expect(isAccessNotGranted(new ApiError(401, 'ACCESS_NOT_GRANTED', 'x'))).toBe(false);
    expect(isAccessNotGranted(new ApiError(500, 'HTTP_ERROR', 'x'))).toBe(false);
    expect(isAccessNotGranted(new TypeError('Failed to fetch'))).toBe(false);
    expect(isAccessNotGranted(null)).toBe(false);
  });

  it('тексты экрана — дословно', () => {
    expect(NO_ACCESS_TEXT).toBe(
      'Доступ пока не открыт. Если у Вас есть промокод — отправьте его боту. Когда бот ответит, нажмите «Проверить ещё раз».',
    );
    expect(NO_ACCESS_BUTTON).toBe('Проверить ещё раз');
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
