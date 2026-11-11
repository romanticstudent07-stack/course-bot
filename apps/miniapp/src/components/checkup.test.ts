// apps/miniapp/src/components/checkup.test.ts — vitest, environment node, без DOM (miniapp-i3-1b §9).
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ApiError, type CheckupConfig } from '../api/client.ts';
import { CheckupQuestionView } from './Checkup.tsx';
import {
  ZONE_FALLBACK_TITLE,
  blockTitle,
  buildSubmitBody,
  checkupErrorAction,
  checkupReducer,
  initialCheckup,
  questionLabel,
  zoneView,
  type CheckupAction,
  type CheckupState,
} from './checkup.ts';

const noop = () => undefined;

const CONFIG: CheckupConfig = {
  version: 'v1-stub',
  scale: { min: 0, max: 3 },
  blocks: [1, 2, 3, 4].map((id) => ({ id, title: `Заглушка: блок ${id}` })),
  questions: Array.from({ length: 15 }, (_, i) => ({
    id: `q${String(i + 1).padStart(2, '0')}`,
    block: Math.floor(i / 4) + 1,
    text: `Заглушка: утверждение ${i + 1}.`,
  })),
  zones: [
    { id: 'green', title: 'Заглушка: зелёная зона', text: 'Заглушка: расшифровка зелёной зоны.' },
    { id: 'red', title: 'Заглушка: красная зона', text: 'Заглушка: расшифровка красной зоны.' },
  ],
  disclaimer: 'Заглушка: дисклеймер.',
};

function run(state: CheckupState, ...actions: CheckupAction[]): CheckupState {
  return actions.reduce(checkupReducer, state);
}

function answerAll(values: number[]): CheckupState {
  return run(initialCheckup(values.length), ...values.map((value, index) => ({ type: 'answer' as const, index, value })));
}

describe('checkupReducer', () => {
  it('1. answer: ответ записан, индекс +1; answer со старым index — без изменений', () => {
    const s1 = run(initialCheckup(15), { type: 'answer', index: 0, value: 2 });
    expect(s1.index).toBe(1);
    expect(s1.answers[0]).toBe(2);
    const s2 = run(s1, { type: 'answer', index: 0, value: 3 });
    expect(s2).toBe(s1);
  });

  it('2. fix: индекс −1, прежний ответ сохранён; на первом вопросе — без изменений', () => {
    const s1 = run(initialCheckup(15), { type: 'answer', index: 0, value: 1 }, { type: 'fix' });
    expect(s1.index).toBe(0);
    expect(s1.answers[0]).toBe(1);
    const s0 = initialCheckup(15);
    expect(run(s0, { type: 'fix' })).toBe(s0);
  });

  it('3. новый ответ после fix заменяет прежний, остальные сохранены', () => {
    const s = run(
      initialCheckup(15),
      { type: 'answer', index: 0, value: 1 },
      { type: 'answer', index: 1, value: 2 },
      { type: 'answer', index: 2, value: 3 },
      { type: 'fix' },
      { type: 'fix' },
      { type: 'answer', index: 1, value: 0 },
    );
    expect(s.index).toBe(2);
    expect(s.answers.slice(0, 3)).toEqual([1, 0, 3]);
  });
});

describe('подписи', () => {
  it('4. questionLabel', () => {
    expect(questionLabel(0, 15)).toBe('Вопрос 1 из 15');
    expect(questionLabel(14, 15)).toBe('Вопрос 15 из 15');
  });

  it('5. blockTitle: title по question.block', () => {
    expect(blockTitle(CONFIG, CONFIG.questions[0])).toBe('Заглушка: блок 1');
    expect(blockTitle(CONFIG, CONFIG.questions[14])).toBe('Заглушка: блок 4');
  });
});

describe('buildSubmitBody', () => {
  it('6. {occasion, answers} — 15 целых 0–3; ответов меньше 15 → null', () => {
    const values = Array.from({ length: 15 }, (_, i) => i % 4);
    const body = buildSubmitBody(answerAll(values));
    expect(body).toEqual({ occasion: 'onboarding', answers: values });
    expect(body?.answers).toHaveLength(15);
    for (const a of body?.answers ?? []) {
      expect(Number.isInteger(a) && a >= 0 && a <= 3).toBe(true);
    }
    const partial = run(initialCheckup(15), { type: 'answer', index: 0, value: 1 });
    expect(buildSubmitBody(partial)).toBeNull();
  });
});

describe('checkupErrorAction', () => {
  it('7. коды контракта', () => {
    expect(checkupErrorAction(new ApiError(409, 'CHECKUP_EXISTS', ''))).toBe('done');
    expect(checkupErrorAction(new ApiError(409, 'IDEMPOTENCY_CONFLICT', ''))).toBe('conflict');
    expect(checkupErrorAction(new ApiError(409, 'RECONSENT_REQUIRED', ''))).toBe('restart');
    expect(checkupErrorAction(new ApiError(404, 'PARTICIPANT_NOT_FOUND', ''))).toBe('restart');
    expect(checkupErrorAction(new ApiError(422, 'VALIDATION_ERROR', ''))).toBe('invalid');
    expect(checkupErrorAction(new ApiError(503, 'SERVICE_UNAVAILABLE', ''))).toBe('retry');
    expect(checkupErrorAction(new TypeError('Failed to fetch'))).toBe('retry');
  });
});

describe('zoneView', () => {
  it('8. зона из config → title и text; неизвестная → заглушка; баллов нет', () => {
    const green = zoneView(CONFIG, 'green');
    expect(green).toEqual({ title: 'Заглушка: зелёная зона', text: 'Заглушка: расшифровка зелёной зоны.' });
    const unknown = zoneView(CONFIG, 'purple');
    expect(unknown.title).toBe(ZONE_FALLBACK_TITLE);
    for (const v of [green, unknown]) {
      expect(`${v.title} ${v.text}`).not.toMatch(/\d/);
    }
  });
});

describe('CheckupQuestionView', () => {
  it('9. 4 кнопки 0–3, «Вопрос N из 15», отмеченный ответ', () => {
    const state = run(
      initialCheckup(15),
      { type: 'answer', index: 0, value: 1 },
      { type: 'answer', index: 1, value: 2 },
      { type: 'fix' },
    );
    const html = renderToStaticMarkup(
      createElement(CheckupQuestionView, { config: CONFIG, state, onAnswer: noop, onFix: noop }),
    );
    expect(html).toContain('Вопрос 2 из 15');
    const scale = (html.match(/<button[^>]*aria-pressed="(true|false)"[^>]*>[^<]*<\/button>/g) ?? []);
    expect(scale).toHaveLength(4);
    expect(scale.map((b) => b.replace(/<[^>]+>/g, '').replace('✓ ', ''))).toEqual(['0', '1', '2', '3']);
    const pressed = scale.filter((b) => b.includes('aria-pressed="true"'));
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toContain('✓ 2');
    expect(html).not.toContain('<input');
  });
});
