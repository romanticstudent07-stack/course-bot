// apps/miniapp/src/components/ErrorBoundary.test.ts — vitest, environment node (miniapp-fix-1, D-23).
// При сбое — нейтральный текст; error.message не попадает ни на экран, ни в лог.
// renderToStaticMarkup границу ошибок не вызывает — поэтому state задаём руками.
import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { ErrorBoundary, NeutralErrorFallback } from './ErrorBoundary.tsx';

const MARKER = 'MARKER-d23';
const TEXT = 'Что-то пошло не так. Закройте приложение и откройте заново.';

function makeBoundary(): ErrorBoundary {
  return new ErrorBoundary({
    fallback: NeutralErrorFallback,
    children: createElement('p', null, 'child'),
  });
}

describe('NeutralErrorFallback', () => {
  it('показывает текст-заглушку', () => {
    const html = renderToStaticMarkup(createElement(NeutralErrorFallback));
    expect(html).toContain(TEXT);
  });
});

describe('ErrorBoundary', () => {
  it('после ошибки: текст-заглушка есть, message нет', () => {
    const state = ErrorBoundary.getDerivedStateFromError(new Error(MARKER));
    const instance = makeBoundary();
    instance.state = state ?? {};
    const html = renderToStaticMarkup(instance.render() as ReactElement);
    expect(html).toContain(TEXT);
    expect(html).not.toContain(MARKER);
    expect(html).not.toContain('child');
  });

  it('без ошибки — дети', () => {
    const html = renderToStaticMarkup(makeBoundary().render() as ReactElement);
    expect(html).toContain('child');
    expect(html).not.toContain(TEXT);
  });

  it('componentDidCatch: в лог только имя класса, без message', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    try {
      const instance = makeBoundary();
      instance.componentDidCatch(new Error(MARKER));
      instance.componentDidCatch(MARKER);
      const logged = spy.mock.calls.flat().map(String).join(' ');
      expect(logged).not.toContain(MARKER);
      expect(logged).toContain('Error');
      expect(logged).toContain('string');
    } finally {
      spy.mockRestore();
    }
  });
});
