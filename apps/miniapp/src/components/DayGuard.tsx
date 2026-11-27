// apps/miniapp/src/components/DayGuard.tsx — охрана экрана /day (miniapp-pause-c3b §7.2, регрессия 4 t5-bc §4).
// При монтировании — один checkDayAccess(getPause, Date.now()); пока ждём — «Загрузка…».
// open → children. paused → строка «Пауза активна» без перехода: маршрута /paused ещё нет (c3b-2),
// а переход попал бы в path="*" → /day → снова сюда, то есть петля. Переход на /paused включит c3b-2.
// error → текст dayErrorMessage и «Повторить»: кнопка disabled, пока !canRetry; таймер только
// включает кнопку и GET не делает; по нажатию — проверка canRetry и ровно один checkDayAccess.
// Повтор с отсрочкой экрана дня здесь не применяется (§7.2). Ответ GET живёт только в state React.
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

import { getPause } from '../api/client.ts';
import { canRetry, checkDayAccess, type DayAccess } from './dayAccess.ts';
import { dayErrorMessage } from './dayScreen.ts';

export const DAY_GUARD_PAUSED_TEXT = 'Пауза активна';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };

export interface DayGuardErrorViewProps {
  text: string;
  retryEnabled: boolean;
  onRetry: () => void;
}

/** Вид ошибки без хуков: текст и «Повторить» (disabled, пока повтор нельзя). */
export function DayGuardErrorView({ text, retryEnabled, onRetry }: DayGuardErrorViewProps) {
  return (
    <div className="page" style={pageStyle}>
      <p>{text}</p>
      <button type="button" disabled={!retryEnabled} onClick={onRetry}>
        Повторить
      </button>
    </div>
  );
}

export function DayGuard({ children }: { children: ReactNode }) {
  const [access, setAccess] = useState<DayAccess | null>(null);
  const [retryEnabled, setRetryEnabled] = useState(false);

  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  const check = useCallback(() => {
    const id = ++requestIdRef.current;
    setAccess(null);
    setRetryEnabled(false);
    void checkDayAccess(getPause, Date.now()).then((result: DayAccess) => {
      if (!mountedRef.current || id !== requestIdRef.current) return;
      setAccess(result);
      setRetryEnabled(canRetry(result, Date.now()));
    });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    check();
    return () => {
      mountedRef.current = false;
    };
  }, [check]);

  useEffect(() => {
    if (access === null || access.kind !== 'error' || retryEnabled) return undefined;
    const wait = Math.max(0, access.retryAt - Date.now());
    const timer = setTimeout(() => setRetryEnabled(true), wait);
    return () => clearTimeout(timer);
  }, [access, retryEnabled]);

  const onRetry = useCallback(() => {
    if (access === null || !canRetry(access, Date.now())) return;
    check();
  }, [access, check]);

  if (access === null) {
    return (
      <div className="page" style={pageStyle}>
        <p>Загрузка…</p>
      </div>
    );
  }

  if (access.kind === 'open') return <>{children}</>;

  if (access.kind === 'paused') {
    return (
      <div className="page" style={pageStyle}>
        <p>{DAY_GUARD_PAUSED_TEXT}</p>
      </div>
    );
  }

  return <DayGuardErrorView text={dayErrorMessage(access.error)} retryEnabled={retryEnabled} onRetry={onRetry}/>;
}
