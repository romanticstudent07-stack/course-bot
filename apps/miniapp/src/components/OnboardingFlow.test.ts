// apps/miniapp/src/components/OnboardingFlow.test.ts — vitest, environment node, без DOM.
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
import { readFileSync } from 'node:fs';

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../api/client.ts';
import {
  AgeGateView,
  ConsentView,
  INITIAL_STATE,
  ONBOARDING_TEXT_KEYS,
  REQUIRED_CONSENTS,
  buildFirstLaunchBody,
  canContinueAgeGate,
  canSubmit,
  isBirthDateFilled,
  pickText,
  screenAfterError,
  textsToMap,
  type OnboardingState,
} from './OnboardingFlow.tsx';

const noop = () => undefined;
const VALID_DATE = '1990-05-17';
const BUTTON_DISABLED_RE = /<button[^>]*\sdisabled=""/;

function full(): OnboardingState {
  return { ageConfirmed: true, birthDate: VALID_DATE, pdnConsent: true };
}

function renderAgeGate(state: OnboardingState): string {
  return renderToStaticMarkup(
    createElement(AgeGateView, {
      text: 'age-gate',
      c0Label: 'c0',
      state,
      onAgeConfirmedChange: noop,
      onBirthDateChange: noop,
      onContinue: noop,
    }),
  );
}

function renderConsent(state: OnboardingState, submitting = false): string {
  return renderToStaticMarkup(
    createElement(ConsentView, {
      intro: 'intro',
      c1Label: 'c1',
      state,
      submitting,
      onPdnConsentChange: noop,
      onContinue: noop,
    }),
  );
}

describe('INITIAL_STATE', () => {
  it('все галочки выключены, дата пустая', () => {
    expect(INITIAL_STATE).toEqual({ ageConfirmed: false, birthDate: '', pdnConsent: false });
  });
});

describe('isBirthDateFilled', () => {
  it('верные значения', () => {
    expect(isBirthDateFilled(VALID_DATE)).toBe(true);
    expect(isBirthDateFilled('2000-02-29')).toBe(true);
    // возраст и «будущее» клиент не считает — это сервер (403 / 422)
    expect(isBirthDateFilled('2999-01-01')).toBe(true);
  });

  it('неверные значения', () => {
    for (const bad of ['', '1990-5-17', '17.05.1990', '1990-02-30', '2001-02-29', '1990-13-01',
      '1990-00-10', '1990-05-00', '1990-05-17T00:00', ' 1990-05-17', 'abcd-ef-gh']) {
      expect(isBirthDateFilled(bad)).toBe(false);
    }
  });
});

describe('canSubmit / canContinueAgeGate', () => {
  it('всё отмечено и дата есть → true', () => {
    expect(canSubmit(full())).toBe(true);
    expect(canContinueAgeGate(full())).toBe(true);
  });

  it('чего-то не хватает → false', () => {
    expect(canSubmit(INITIAL_STATE)).toBe(false);
    expect(canSubmit({ ...full(), ageConfirmed: false })).toBe(false);
    expect(canSubmit({ ...full(), pdnConsent: false })).toBe(false);
    expect(canSubmit({ ...full(), birthDate: '' })).toBe(false);
    expect(canSubmit({ ...full(), birthDate: '1990-02-30' })).toBe(false);
    expect(canContinueAgeGate({ ...full(), ageConfirmed: false })).toBe(false);
    expect(canContinueAgeGate({ ...full(), birthDate: '' })).toBe(false);
  });
});

describe('AgeGateView: кнопка «Продолжить»', () => {
  it('disabled, пока нет галочки C0 и даты', () => {
    expect(renderAgeGate(INITIAL_STATE)).toMatch(BUTTON_DISABLED_RE);
    expect(renderAgeGate({ ...INITIAL_STATE, ageConfirmed: true })).toMatch(BUTTON_DISABLED_RE);
    expect(renderAgeGate({ ...INITIAL_STATE, birthDate: VALID_DATE })).toMatch(BUTTON_DISABLED_RE);
  });

  it('активна, когда галочка C0 отмечена и дата заполнена', () => {
    const html = renderAgeGate({ ...INITIAL_STATE, ageConfirmed: true, birthDate: VALID_DATE });
    expect(html).not.toMatch(BUTTON_DISABLED_RE);
    expect(html).toContain('type="date"');
  });

  it('галочка по умолчанию не отмечена', () => {
    expect(renderAgeGate(INITIAL_STATE)).not.toContain('checked=""');
  });
});

describe('ConsentView: кнопка «Продолжить»', () => {
  it('disabled, пока не отмечены обе галочки и не заполнена дата', () => {
    expect(renderConsent(INITIAL_STATE)).toMatch(BUTTON_DISABLED_RE);
    expect(renderConsent({ ...full(), pdnConsent: false })).toMatch(BUTTON_DISABLED_RE);
    expect(renderConsent({ ...full(), ageConfirmed: false })).toMatch(BUTTON_DISABLED_RE);
    expect(renderConsent({ ...full(), birthDate: '' })).toMatch(BUTTON_DISABLED_RE);
  });

  it('активна, когда всё отмечено', () => {
    expect(renderConsent(full())).not.toMatch(BUTTON_DISABLED_RE);
  });

  it('disabled, пока идёт отправка (защита от двойного клика)', () => {
    expect(renderConsent(full(), true)).toMatch(BUTTON_DISABLED_RE);
  });
});

describe('buildFirstLaunchBody', () => {
  it('даёт {birth_date, consents: [C0, C1]}', () => {
    expect(buildFirstLaunchBody(full())).toEqual({ birth_date: VALID_DATE, consents: ['C0', 'C1'] });
    expect(REQUIRED_CONSENTS).toEqual(['C0', 'C1']);
  });
});

describe('screenAfterError', () => {
  it('коды контракта', () => {
    expect(screenAfterError(new ApiError(403, 'AGE_GATE_UNDERAGE', ''))).toBe('underage');
    expect(screenAfterError(new ApiError(422, 'CONSENTS_REQUIRED', ''))).toBe('consent');
    expect(screenAfterError(new ApiError(422, 'CONSENT_NOT_SUPPORTED', ''))).toBe('consent');
    expect(screenAfterError(new ApiError(422, 'BIRTH_DATE_IN_FUTURE', ''))).toBe('age-gate');
  });

  it('прочее → error', () => {
    expect(screenAfterError(new ApiError(401, 'TG_INIT_INVALID', ''))).toBe('error');
    expect(screenAfterError(new ApiError(429, 'HTTP_ERROR', ''))).toBe('error');
    expect(screenAfterError(new ApiError(503, 'SERVICE_UNAVAILABLE', ''))).toBe('error');
    expect(screenAfterError(new TypeError('Failed to fetch'))).toBe('error');
    expect(screenAfterError(undefined)).toBe('error');
  });
});

describe('тексты', () => {
  it('ONBOARDING_TEXT_KEYS — ровно 7 ключей контракта', () => {
    expect(ONBOARDING_TEXT_KEYS).toHaveLength(7);
    expect([...ONBOARDING_TEXT_KEYS].sort()).toEqual([
      'B4.onb_age_gate',
      'B4.onb_age_underage',
      'B4.onb_done',
      'B4.onb_welcome',
      'legal.consent_c0_age_18_plus',
      'legal.consent_c1_pdn',
      'legal.onb_consent_intro',
    ]);
  });

  it('pickText: есть ключ → текст, нет → заглушка', () => {
    const map = textsToMap({
      texts: [{ key: 'B4.onb_welcome', tone: 'neutral', legal_status: 'stub', text: 'Привет' }],
      missing: ['B4.onb_done'],
    });
    expect(pickText(map, 'B4.onb_welcome')).toBe('Привет');
    expect(pickText(map, 'B4.onb_done')).toBe('[текст не загружен: B4.onb_done]');
    expect(pickText({}, 'legal.consent_c1_pdn')).toBe('[текст не загружен: legal.consent_c1_pdn]');
  });
});

describe('дата не уходит в хранилище', () => {
  it('в исходнике OnboardingFlow.tsx нет хранилищ и console.log', () => {
    const source = readFileSync(new URL('./OnboardingFlow.tsx', import.meta.url), 'utf8').toLowerCase();
    for (const banned of ['localstorage', 'sessionstorage', 'indexeddb', 'dexie', 'document.cookie', 'console.log']) {
      expect(source.includes(banned), banned).toBe(false);
    }
  });
});
