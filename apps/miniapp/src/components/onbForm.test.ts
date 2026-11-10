// apps/miniapp/src/components/onbForm.test.ts — vitest, environment node, без DOM (miniapp-i3-1a §9).
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
import { readFileSync } from 'node:fs';

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ApiError, type FormCity, type FormConfig } from '../api/client.ts';
import { OnbFormView } from './OnbForm.tsx';
import {
  INITIAL_FORM,
  buildFormBody,
  cityLines,
  formErrorAction,
  formReducer,
  normalizeQuery,
  parseWeight,
  suggestCities,
  type FormAction,
  type FormState,
} from './onbForm.ts';

const WEIGHT = { min: 30, max: 300, step: 0.1 };
const noop = () => undefined;

const CONFIG: FormConfig = {
  version: 1,
  genders: ['male', 'female'],
  wellbeing_question: 'Заглушка: самочувствие?',
  wellbeing: [
    { code: 'good', text: 'Заглушка: хорошо' },
    { code: 'bad', text: 'Заглушка: плохо' },
  ],
  weight: WEIGHT,
  timezones: [
    { tz: 'Europe/Moscow', city: 'Москва' },
    { tz: 'Asia/Yekaterinburg', city: 'Екатеринбург' },
  ],
  fallback_title: 'Заглушка: выберите пояс',
  cities: [
    ['Москва', 'Москва', 0],
    ['Екатеринбург', 'Свердловская область', 1],
  ],
};

function run(state: FormState, ...actions: FormAction[]): FormState {
  return actions.reduce(formReducer, state);
}

function filled(): FormState {
  return run(
    INITIAL_FORM,
    { type: 'pickCity', city: 'Москва', tz: 'Europe/Moscow' },
    { type: 'setGender', gender: 'female' },
    { type: 'setWellbeing', code: 'good' },
    { type: 'setWeight', text: '72,5' },
  );
}

function renderView(state: FormState): string {
  return renderToStaticMarkup(
    createElement(OnbFormView, { config: CONFIG, state, submitting: false, notice: null, onAction: noop, onYes: noop }),
  );
}

describe('1. normalizeQuery', () => {
  it('регистр, ё → е, крайние пробелы', () => {
    expect(normalizeQuery('  МоСКВа ')).toBe('москва');
    expect(normalizeQuery('Орёл')).toBe('орел');
    expect(normalizeQuery('ЁЛКИ')).toBe('елки');
  });
});

describe('2. suggestCities', () => {
  const many: FormCity[] = Array.from({ length: 15 }, (_, i) => [`Сан${i}`, 'Регион', 0] as FormCity);
  const cities: FormCity[] = [['Самара', 'Самарская область', 0], ['Новосамарск', 'X', 0], ...many];

  it('1 символ → []', () => {
    expect(suggestCities(cities, 'С')).toEqual([]);
  });

  it('совпадение только с начала названия', () => {
    const names = suggestCities(cities, 'сама').map((c) => c[0]);
    expect(names).toEqual(['Самара']);
  });

  it('не больше 10, в порядке cities', () => {
    const out = suggestCities(cities, 'сан');
    expect(out).toHaveLength(10);
    expect(out.map((c) => c[0])).toEqual(many.slice(0, 10).map((c) => c[0]));
  });
});

describe('3. cityLines', () => {
  it('регион = город → одна строка; иначе две', () => {
    expect(cityLines(['Москва', 'Москва', 0])).toEqual(['Москва']);
    expect(cityLines(['Екатеринбург', 'Свердловская область', 1])).toEqual(['Екатеринбург', 'Свердловская область']);
  });
});

describe('4. parseWeight', () => {
  it('запятая, знаки после точки, диапазон, мусор', () => {
    expect(parseWeight('72,5', WEIGHT)).toBe(72.5);
    expect(parseWeight('72.55', WEIGHT)).toBeNull();
    expect(parseWeight('29.9', WEIGHT)).toBeNull();
    expect(parseWeight('300.1', WEIGHT)).toBeNull();
    expect(parseWeight('abc', WEIGHT)).toBeNull();
    expect(parseWeight('', WEIGHT)).toBeNull();
  });
});

describe('5. formReducer', () => {
  it('правка текста сбрасывает tz', () => {
    const s = run(INITIAL_FORM, { type: 'pickCity', city: 'Москва', tz: 'Europe/Moscow' });
    expect(s.tz).toBe('Europe/Moscow');
    expect(run(s, { type: 'setQuery', query: 'Москв' }).tz).toBeNull();
  });

  it('«Моего города нет» + выбор ставит tz', () => {
    const s = run(INITIAL_FORM, { type: 'openFallback' }, { type: 'pickTz', tz: 'Asia/Yekaterinburg', place: 'Екатеринбург' });
    expect(s.fallbackOpen).toBe(true);
    expect(s.tz).toBe('Asia/Yekaterinburg');
  });

  it('без одного поля «всё верно?» не открывается', () => {
    const full = filled();
    const missing: FormState[] = [
      { ...full, tz: null },
      { ...full, gender: null },
      { ...full, wellbeing: null },
      { ...full, weightText: '' },
    ];
    for (const s of missing) expect(run(s, { type: 'confirm', weight: WEIGHT }).screen).toBe('fields');
    expect(run(full, { type: 'confirm', weight: WEIGHT }).screen).toBe('confirm');
  });

  it('«Исправить» сохраняет значения', () => {
    const confirmed = run(filled(), { type: 'confirm', weight: WEIGHT });
    const edited = run(confirmed, { type: 'edit' });
    expect(edited).toEqual({ ...confirmed, screen: 'fields' });
  });
});

describe('6. buildFormBody', () => {
  it('ключи ровно gender, tz, weight_kg, wellbeing_code (города нет)', () => {
    const body = buildFormBody(filled(), WEIGHT);
    expect(body).not.toBeNull();
    expect(Object.keys(body ?? {}).sort()).toEqual(['gender', 'tz', 'weight_kg', 'wellbeing_code']);
    expect(body).toEqual({ tz: 'Europe/Moscow', gender: 'female', wellbeing_code: 'good', weight_kg: 72.5 });
  });
});

describe('7. formErrorAction', () => {
  it('коды контракта', () => {
    expect(formErrorAction(new ApiError(409, 'ONBOARDING_FORM_EXISTS', ''))).toBe('done');
    expect(formErrorAction(new ApiError(409, 'IDEMPOTENCY_CONFLICT', ''))).toBe('conflict');
    expect(formErrorAction(new ApiError(409, 'RECONSENT_REQUIRED', ''))).toBe('restart');
    expect(formErrorAction(new ApiError(404, 'PARTICIPANT_NOT_FOUND', ''))).toBe('restart');
    expect(formErrorAction(new ApiError(422, 'VALIDATION_ERROR', ''))).toBe('invalid');
    expect(formErrorAction(new ApiError(503, 'SERVICE_UNAVAILABLE', ''))).toBe('retry');
    expect(formErrorAction(new TypeError('Failed to fetch'))).toBe('retry');
  });
});

describe('8. OnbFormView', () => {
  it('экран подтверждения — «Да» и «Исправить»', () => {
    const html = renderView(run(filled(), { type: 'confirm', weight: WEIGHT }));
    expect(html).toContain('>Да<');
    expect(html).toContain('>Исправить<');
  });

  it('без веса «Далее» disabled', () => {
    const html = renderView({ ...filled(), weightText: '' });
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Далее<\/button>/);
  });
});

describe('9. исходники без console', () => {
  it.each(['./OnbForm.tsx', './onbForm.ts'])('%s: нет console.', (path) => {
    const text = readFileSync(new URL(path, import.meta.url), 'utf8');
    expect(text.includes('console.')).toBe(false);
  });
});
