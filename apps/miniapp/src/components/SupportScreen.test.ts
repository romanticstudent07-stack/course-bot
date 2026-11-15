// SupportScreen.test.ts — экран «Помощь» (miniapp-sup-1, Р-19): темы, проверка текста, ошибки,
// op_id, Retry-After, рендер шагов и запреты подстрок в исходнике SupportScreen.tsx.
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, parseRetryAfter } from '../api/client.ts';
import { SUPPORT_TOPIC_CODES } from './drafts.ts';
import {
  SUPPORT_ERROR_AUTH,
  SUPPORT_ERROR_LATER,
  SUPPORT_ERROR_OTHER,
  SUPPORT_ERROR_TEXT,
  SUPPORT_ERROR_UNAVAILABLE,
  SUPPORT_TOPICS,
  SupportQuestionView,
  SupportTopicView,
  opIdForSend,
  supportErrorView,
  validateSupportText,
} from './SupportScreen.tsx';

const noop = () => undefined;

describe('SUPPORT_TOPICS', () => {
  it('8 тем, коды по порядку, подписи-заглушки Р-19', () => {
    expect(SUPPORT_TOPICS).toHaveLength(8);
    expect(SUPPORT_TOPICS.map((t) => t.code)).toEqual([...SUPPORT_TOPIC_CODES]);
    expect(SUPPORT_TOPICS.map((t) => t.label)).toEqual([
      'Поддержка 1',
      'Поддержка 2',
      'Поддержка 3',
      'Поддержка 4',
      'Поддержка 5',
      'Поддержка 6',
      'Поддержка 7',
      'Другое',
    ]);
  });
});

describe('validateSupportText', () => {
  it('минимум 2 знака после trim', () => {
    expect(validateSupportText('')).toBe('short');
    expect(validateSupportText(' a ')).toBe('short');
    expect(validateSupportText('ab')).toBe('ok');
    expect(validateSupportText(' ab ')).toBe('ok');
  });

  it('максимум 2000 кодовых точек по сырому тексту', () => {
    expect(validateSupportText('😀'.repeat(2000))).toBe('ok');
    expect(validateSupportText('a'.repeat(2001))).toBe('long');
    expect(validateSupportText(`${'a'.repeat(1999)}  `)).toBe('long');
  });

  it('NUL → nul', () => {
    expect(validateSupportText('a\u0000b')).toBe('nul');
  });
});

describe('supportErrorView', () => {
  it('401', () => {
    expect(supportErrorView(new ApiError(401, 'UNAUTHORIZED', 'x'))).toEqual({ kind: 'message', text: SUPPORT_ERROR_AUTH });
  });

  it('404 PARTICIPANT_NOT_FOUND и 409 RECONSENT_REQUIRED → restart', () => {
    expect(supportErrorView(new ApiError(404, 'PARTICIPANT_NOT_FOUND', 'x'))).toEqual({ kind: 'restart' });
    expect(supportErrorView(new ApiError(409, 'RECONSENT_REQUIRED', 'x'))).toEqual({ kind: 'restart' });
  });

  it('каждый код 422', () => {
    for (const code of ['VALIDATION_ERROR', 'SUPPORT_TOPIC_INVALID', 'SUPPORT_TEXT_INVALID']) {
      expect(supportErrorView(new ApiError(422, code, 'x'))).toEqual({ kind: 'message', text: SUPPORT_ERROR_TEXT });
    }
  });

  it('429 с Retry-After и без', () => {
    const withN = supportErrorView(new ApiError(429, 'SUPPORT_TOO_FREQUENT', 'x', 7));
    expect(withN.kind).toBe('message');
    expect(withN.kind === 'message' ? withN.text : '').toContain('7');
    expect(supportErrorView(new ApiError(429, 'RATE_LIMITED', 'x', null))).toEqual({
      kind: 'message',
      text: SUPPORT_ERROR_LATER,
    });
  });

  it('503, ошибка сети, прочее', () => {
    expect(supportErrorView(new ApiError(503, 'SERVICE_UNAVAILABLE', 'x'))).toEqual({
      kind: 'message',
      text: SUPPORT_ERROR_UNAVAILABLE,
    });
    expect(supportErrorView(new TypeError('Failed to fetch'))).toEqual({
      kind: 'message',
      text: SUPPORT_ERROR_UNAVAILABLE,
    });
    expect(supportErrorView(new ApiError(500, 'HTTP_ERROR', 'x'))).toEqual({ kind: 'message', text: SUPPORT_ERROR_OTHER });
  });
});

describe('opIdForSend', () => {
  it('null → новый id', () => {
    const gen = vi.fn(() => 'new-id');
    expect(opIdForSend(null, gen)).toBe('new-id');
    expect(gen).toHaveBeenCalledTimes(1);
  });

  it('есть id → тот же, gen не вызван', () => {
    const gen = vi.fn(() => 'new-id');
    expect(opIdForSend('same-id', gen)).toBe('same-id');
    expect(gen).not.toHaveBeenCalled();
  });
});

describe('parseRetryAfter', () => {
  it('целое > 0 → число', () => {
    expect(parseRetryAfter('7')).toBe(7);
  });

  it('прочее → null', () => {
    for (const v of [null, '', '0', '-1', '1.5', 'abc', 'Wed, 21 Oct 2015 07:28:00 GMT']) {
      expect(parseRetryAfter(v)).toBeNull();
    }
  });
});

describe('рендер', () => {
  it('SupportTopicView: 8 тем + «Назад», выбранная aria-pressed="true"', () => {
    const html = renderToStaticMarkup(createElement(SupportTopicView, { selected: 's2', onPick: noop, onBack: noop }));
    expect(html.match(/<button/g)).toHaveLength(9);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-pressed="true"[^>]*>Поддержка 2</);
    expect(html).toContain('Назад');
  });

  it('SupportQuestionView: тема, поле, «Отправить» неактивна при тексте из 1 знака', () => {
    const html = renderToStaticMarkup(
      createElement(SupportQuestionView, {
        topic: 's1',
        text: 'a',
        sending: false,
        error: null,
        onText: noop,
        onSend: noop,
        onBack: noop,
        onRestart: noop,
      }),
    );
    expect(html).toContain('Поддержка 1');
    expect(html).toContain('<textarea');
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Отправить</);
  });
});

describe('исходник SupportScreen.tsx', () => {
  const src = readFileSync(new URL('./SupportScreen.tsx', import.meta.url), 'utf8').toLowerCase();

  it('нет хранилищ и логов в обход drafts.ts', () => {
    const banned = [
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
    for (const s of banned) expect(src).not.toContain(s);
  });

  it('нет вставки HTML', () => {
    for (const s of ['innerhtml', 'insertadjacenthtml', 'document.write']) expect(src).not.toContain(s);
  });
});
