// apps/miniapp/src/components/ErrorBoundary.tsx — граница ошибок (шаблон + miniapp-fix-1, D-23).
// Пользователю — нейтральный текст без error.message; в лог — только имя класса ошибки.
import {
  Component,
  type ComponentType,
  type GetDerivedStateFromError,
  type PropsWithChildren,
  type ReactNode,
} from 'react';

export interface ErrorBoundaryProps extends PropsWithChildren {
  fallback?: ReactNode | ComponentType<{ error: unknown }>;
}

interface ErrorBoundaryState {
  error?: unknown;
}

/** Экран при сбое: проп error не читает (ни message, ни stack на экран не попадают). */
export function NeutralErrorFallback() {
  return (
    <div className="page">
      <p>Что-то пошло не так. Закройте приложение и откройте заново.</p>
    </div>
  );
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {};

  // eslint-disable-next-line max-len
  static getDerivedStateFromError: GetDerivedStateFromError<ErrorBoundaryProps, ErrorBoundaryState> = (error) => ({ error });

  componentDidCatch(error: unknown) {
    // Только имя класса: message, stack и componentStack не логируем (могут быть ПДн).
    // Не constructor.name — Vite сжимает имена классов.
    const name = error instanceof Error ? error.name : typeof error;
    console.error('ErrorBoundary:', name);
  }

  render() {
    const {
      state: {
        error,
      },
      props: {
        fallback: Fallback,
        children,
      },
    } = this;

    return 'error' in this.state
      ? typeof Fallback === 'function'
        ? <Fallback error={error} />
        : Fallback
      : children;
  }
}
