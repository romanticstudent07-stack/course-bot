// apps/miniapp/src/components/OnboardingFlow.test.ts — vitest, environment node, без DOM.
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
// Компоненты без хуков (AgeGateView, ConsentView, LaterStepView) вызываются как функции,
// чтобы достать onSubmit формы и проверить Enter (отправку формы) без DOM.
import { readFileSync } from 'node:fs';

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, tgUserIdFromInitData, type ConsentOut } from '../api/client.ts';
import { EMPTY_DRAFT, type Draft } from './drafts.ts';
import {
  LATER_TEXT_KEY_LIST,
  LaterStepView,
  activeConsentIds,
  canContinueEmail,
  canGoNext,
  consentsLabel,
  laterReducer,
  progressLabel,
  textKeyFor,
  type LaterAction,
} from './LaterSteps.tsx';
import {
  AgeGateView,
  ConsentView,
  INITIAL_STATE,
  ONBOARDING_TEXT_KEYS,
  REQUIRED_CONSENTS,
  TEXTS_429_MESSAGE,
  TEXTS_NETWORK_MESSAGE,
  buildFirstLaunchBody,
  canContinueAgeGate,
  canSubmit,
  errorMessage,
  isBirthDateFilled,
  makeSubmitHandler,
  pickText,
  screenAfterError,
  textsErrorMessage,
  textsToMap,
  type OnboardingState,
} from './OnboardingFlow.tsx';

const noop = () => undefined;
const VALID_DATE = '1990-05-17';
const BUTTON_DISABLED_RE = /<button[^>]*\sdisabled=""/;
const SUBMIT_DISABLED_RE = /<button[^>]*type="submit"[^>]*\sdisabled=""/;

function full(): OnboardingState {
  return { ageConfirmed: true, birthDate: VALID_DATE, pdnConsent: true };
}

function ageGateProps(state: OnboardingState, onContinue: () => void = noop) {
  return {
    text: 'age-gate',
    c0Label: 'c0',
    state,
    onAgeConfirmedChange: noop,
    onBirthDateChange: noop,
    onContinue,
  };
}

function consentProps(state: OnboardingState, submitting = false, onContinue: () => void = noop) {
  return {
    intro: 'intro',
    c1Label: 'c1',
    state,
    submitting,
    onPdnConsentChange: noop,
    onContinue,
  };
}

function renderAgeGate(state: OnboardingState): string {
  return renderToStaticMarkup(createElement(AgeGateView, ageGateProps(state)));
}

function renderConsent(state: OnboardingState, submitting = false): string {
  return renderToStaticMarkup(createElement(ConsentView, consentProps(state, submitting)));
}

/** Корневой элемент компонента: тип и onSubmit (если это форма). */
function rootOf(el: { type: unknown; props: unknown }) {
  const props = el.props as { onSubmit?: (e: { preventDefault: () => void }) => void };
  return { type: el.type, onSubmit: props.onSubmit };
}

/** Отправить форму (как Enter): вернуть, был ли вызван preventDefault. */
function submitForm(onSubmit: ((e: { preventDefault: () => void }) => void) | undefined): boolean {
  expect(onSubmit).toBeTypeOf('function');
  const preventDefault = vi.fn();
  onSubmit?.({ preventDefault });
  return preventDefault.mock.calls.length === 1;
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

describe('формы и Enter (поправка ШТАБа 2)', () => {
  it('makeSubmitHandler: всегда preventDefault, onContinue — только при enabled', () => {
    const onContinue = vi.fn();
    expect(submitForm(makeSubmitHandler(false, onContinue))).toBe(true);
    expect(onContinue).not.toHaveBeenCalled();
    expect(submitForm(makeSubmitHandler(true, onContinue))).toBe(true);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it('age-gate — <form>, основная кнопка type="submit"', () => {
    const html = renderAgeGate(INITIAL_STATE);
    expect(html.startsWith('<form')).toBe(true);
    expect(html).toMatch(SUBMIT_DISABLED_RE);
    expect(rootOf(AgeGateView(ageGateProps(INITIAL_STATE))).type).toBe('form');
  });

  it('age-gate: Enter без галочки или без даты не вызывает onContinue', () => {
    for (const state of [INITIAL_STATE, { ...INITIAL_STATE, ageConfirmed: true }, { ...INITIAL_STATE, birthDate: VALID_DATE }]) {
      const onContinue = vi.fn();
      expect(submitForm(rootOf(AgeGateView(ageGateProps(state, onContinue))).onSubmit)).toBe(true);
      expect(onContinue).not.toHaveBeenCalled();
    }
  });

  it('age-gate: Enter при выполненных условиях вызывает onContinue', () => {
    const onContinue = vi.fn();
    submitForm(rootOf(AgeGateView(ageGateProps(full(), onContinue))).onSubmit);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it('consent — <form>, основная кнопка type="submit"', () => {
    const html = renderConsent(INITIAL_STATE);
    expect(html.startsWith('<form')).toBe(true);
    expect(html).toMatch(SUBMIT_DISABLED_RE);
  });

  it('consent: отправка формы при canSubmit=false не вызывает onContinue', () => {
    for (const state of [INITIAL_STATE, { ...full(), pdnConsent: false }, { ...full(), birthDate: '' }]) {
      expect(canSubmit(state)).toBe(false);
      const onContinue = vi.fn();
      expect(submitForm(rootOf(ConsentView(consentProps(state, false, onContinue))).onSubmit)).toBe(true);
      expect(onContinue).not.toHaveBeenCalled();
    }
  });

  it('consent: Enter во время отправки не шлёт второй раз', () => {
    const onContinue = vi.fn();
    submitForm(rootOf(ConsentView(consentProps(full(), true, onContinue))).onSubmit);
    expect(onContinue).not.toHaveBeenCalled();
  });

  it('consent: Enter при canSubmit=true вызывает onContinue', () => {
    const onContinue = vi.fn();
    submitForm(rootOf(ConsentView(consentProps(full(), false, onContinue))).onSubmit);
    expect(onContinue).toHaveBeenCalledTimes(1);
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

describe('textsErrorMessage: ошибка загрузки текстов (поправка ШТАБа 3)', () => {
  it('429 → «Слишком много запросов…»', () => {
    expect(TEXTS_429_MESSAGE).toBe('Слишком много запросов. Подождите минуту и нажмите «Повторить».');
    expect(textsErrorMessage(new ApiError(429, 'RATE_LIMITED', ''))).toBe(TEXTS_429_MESSAGE);
  });

  it('401 и 503 — как errorMessage', () => {
    for (const err of [
      new ApiError(401, 'TG_INIT_INVALID', ''),
      new ApiError(401, 'TG_INIT_MISSING', ''),
      new ApiError(503, 'SERVICE_UNAVAILABLE', ''),
      new ApiError(503, 'SERVICE_MISCONFIGURED', ''),
    ]) {
      expect(textsErrorMessage(err)).toBe(errorMessage(err));
    }
  });

  it('«Проверьте интернет» — только при сетевой ошибке', () => {
    expect(textsErrorMessage(new TypeError('Failed to fetch'))).toBe(TEXTS_NETWORK_MESSAGE);
    expect(textsErrorMessage(undefined)).toBe(TEXTS_NETWORK_MESSAGE);
    expect(TEXTS_NETWORK_MESSAGE).toContain('Проверьте интернет');
    for (const status of [401, 403, 404, 422, 429, 500, 503]) {
      expect(textsErrorMessage(new ApiError(status, 'X', ''))).not.toContain('Проверьте интернет');
    }
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

  it('LATER_TEXT_KEY_LIST — 5 ключей экранов после pid', () => {
    expect([...LATER_TEXT_KEY_LIST].sort()).toEqual([
      'B4.onb_checkup',
      'B4.onb_city',
      'B4.onb_email',
      'B4.onb_rules',
      'legal.offer',
    ]);
    expect(textKeyFor('offer')).toBe('legal.offer');
    expect(textKeyFor('finished')).toBeNull();
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

// ---- LaterSteps: шаги после pid ----

function at(step: Draft['step'], over: Partial<Draft> = {}): Draft {
  return { ...EMPTY_DRAFT, step, ...over };
}

function run(state: Draft, ...actions: LaterAction[]): Draft {
  return actions.reduce(laterReducer, state);
}

function renderLater(draft: Draft, consentsText?: string): string {
  return renderToStaticMarkup(
    createElement(LaterStepView, { draft, text: 'txt', consentsText, onAction: noop, onFinish: noop }),
  );
}

describe('LaterSteps: порядок шагов', () => {
  it('offer → email → city → checkup → rules → finished', () => {
    let s = EMPTY_DRAFT;
    expect(s.step).toBe('offer');
    s = run(s, { type: 'next' });
    expect(s.step).toBe('email');
    s = run(s, { type: 'next' }); // email пустой — можно дальше
    expect(s.step).toBe('city');
    s = run(s, { type: 'next' }); // город не выбран — стоим
    expect(s.step).toBe('city');
    s = run(s, { type: 'setCity', city: 'Москва' }, { type: 'next' });
    expect(s.step).toBe('checkup');
    s = run(s, { type: 'next' }, { type: 'next' });
    expect(s.step).toBe('finished');
    expect(run(s, { type: 'next' }).step).toBe('finished');
  });

  it('«Назад» на шаг раньше; с offer назад некуда', () => {
    expect(run(at('city'), { type: 'back' }).step).toBe('email');
    expect(run(at('offer'), { type: 'back' }).step).toBe('offer');
    expect(run(at('finished'), { type: 'back' }).step).toBe('rules');
  });

  it('email: неверный адрес не пускает дальше, «Пропустить» очищает', () => {
    expect(canContinueEmail('')).toBe(true);
    expect(canContinueEmail('  ')).toBe(true);
    expect(canContinueEmail('a@b.ru')).toBe(true);
    expect(canContinueEmail('abc')).toBe(false);
    const bad = run(at('email'), { type: 'setEmail', email: 'abc' }, { type: 'next' });
    expect(bad.step).toBe('email');
    const skipped = run(bad, { type: 'skipEmail' });
    expect(skipped).toEqual({ ...EMPTY_DRAFT, step: 'city', email: '' });
    const ok = run(at('email'), { type: 'setEmail', email: ' a@b.ru ' }, { type: 'next' });
    expect(ok).toEqual({ ...EMPTY_DRAFT, step: 'city', email: 'a@b.ru' });
  });

  it('city: только город из списка', () => {
    expect(run(at('city'), { type: 'setCity', city: 'Атлантида' }).city).toBe('');
    expect(canGoNext(at('city'))).toBe(false);
    expect(canGoNext(at('city', { city: 'Москва' }))).toBe(true);
    // поля меняются только на своём шаге
    expect(run(at('offer'), { type: 'setEmail', email: 'a@b.ru' }).email).toBe('');
    expect(run(at('offer'), { type: 'setCity', city: 'Москва' }).city).toBe('');
  });

  it('индикатор прогресса', () => {
    expect(progressLabel('offer')).toBe('Шаг 1 из 5');
    expect(progressLabel('rules')).toBe('Шаг 5 из 5');
    expect(progressLabel('finished')).toBe('');
    expect(renderLater(at('checkup'))).toContain('Шаг 4 из 5');
  });

  it('offer: «Назад» неактивна, «Далее» активна; ни оплаты, ни галочки акцепта', () => {
    const html = renderLater(at('offer'));
    expect(html).toMatch(BUTTON_DISABLED_RE);
    expect(html).not.toContain('type="checkbox"');
    expect(html.toLowerCase()).not.toContain('оплат');
  });
});

describe('LaterSteps: формы email и city, Enter', () => {
  it('email и city — <form> с type="submit"', () => {
    for (const step of ['email', 'city'] as const) {
      const html = renderLater(at(step));
      expect(html.startsWith('<form')).toBe(true);
      expect(html).toContain('type="submit"');
    }
    expect(renderLater(at('city'))).toMatch(SUBMIT_DISABLED_RE);
    expect(renderLater(at('email', { email: 'abc' }))).toMatch(SUBMIT_DISABLED_RE);
  });

  it('Enter при невыполненных условиях ничего не делает', () => {
    for (const draft of [at('email', { email: 'abc' }), at('city')]) {
      const onAction = vi.fn();
      const el = LaterStepView({ draft, text: 't', onAction, onFinish: noop });
      expect(rootOf(el).type).toBe('form');
      expect(submitForm(rootOf(el).onSubmit)).toBe(true);
      expect(onAction).not.toHaveBeenCalled();
    }
  });

  it('Enter при выполненных условиях → next', () => {
    for (const draft of [at('email'), at('email', { email: 'a@b.ru' }), at('city', { city: 'Москва' })]) {
      const onAction = vi.fn();
      submitForm(rootOf(LaterStepView({ draft, text: 't', onAction, onFinish: noop })).onSubmit);
      expect(onAction).toHaveBeenCalledWith({ type: 'next' });
    }
  });
});

describe('согласия на экране finished', () => {
  const list: ConsentOut[] = [
    { id: 'C1', given_at: '2026-10-02T12:00:00Z', revoked_at: null, legal_status: 'pre-legal-review' },
    { id: 'C0', given_at: '2026-10-02T12:00:00Z', revoked_at: null, legal_status: 'pre-legal-review' },
    { id: 'C2', given_at: '2026-10-02T12:00:00Z', revoked_at: '2026-10-02T13:00:00Z', legal_status: 'x' },
  ];

  it('только действующие, по порядку', () => {
    expect(activeConsentIds(list)).toEqual(['C0', 'C1']);
    expect(consentsLabel(list)).toBe('Ваши согласия: C0, C1');
    expect(consentsLabel([])).toBe('Ваши согласия: нет');
    expect(consentsLabel('loading')).toContain('загрузка');
    expect(consentsLabel('failed')).toContain('не удалось');
  });

  it('экран finished показывает строку согласий', () => {
    expect(renderLater(at('finished'), 'Ваши согласия: C0, C1')).toContain('Ваши согласия: C0, C1');
  });
});

describe('tgUserIdFromInitData (только для привязки черновика)', () => {
  it('берёт user.id из сырой строки', () => {
    const raw = new URLSearchParams({ user: JSON.stringify({ id: 777, first_name: 'T' }), hash: 'x' }).toString();
    expect(tgUserIdFromInitData(raw)).toBe(777);
  });

  it('нет / битое → null', () => {
    for (const raw of [undefined, '', 'hash=x', 'user=%7Bbad', 'user=%7B%22id%22%3A%22777%22%7D', 'user=%7B%22id%22%3A0%7D']) {
      expect(tgUserIdFromInitData(raw)).toBeNull();
    }
  });
});

// ---- Хранилища и утечки (D-19) ----

const NO_STORAGE_FILES = ['./OnboardingFlow.tsx', './LaterSteps.tsx', './App.tsx', '../api/client.ts'];
const BANNED_STORAGE = [
  'localstorage',
  'sessionstorage',
  'indexeddb',
  'dexie',
  'document.cookie',
  'console.',
  'sendbeacon',
  'pushstate',
  'replacestate',
  'location.hash',
  'persist(',
];
const BANNED_HTML = ['innerhtml', 'insertadjacenthtml', 'document.write'];

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8').toLowerCase();
}

describe('дата и анкета не уходят в хранилище (D-19)', () => {
  it.each(NO_STORAGE_FILES)('%s: нет хранилищ, console и истории', (path) => {
    const text = source(path);
    for (const banned of BANNED_STORAGE) {
      expect(text.includes(banned), `${path}: ${banned}`).toBe(false);
    }
  });

  it.each([...NO_STORAGE_FILES, './drafts.ts'])('%s: нет innerHTML и аналогов (R342)', (path) => {
    const text = source(path);
    for (const banned of BANNED_HTML) {
      expect(text.includes(banned), `${path}: ${banned}`).toBe(false);
    }
  });

  it('drafts.ts: нет даты рождения и console', () => {
    const text = source('./drafts.ts');
    for (const banned of ['birth', 'console.', 'localstorage', 'sessionstorage', 'document.cookie', 'dexie']) {
      expect(text.includes(banned), banned).toBe(false);
    }
  });
});
