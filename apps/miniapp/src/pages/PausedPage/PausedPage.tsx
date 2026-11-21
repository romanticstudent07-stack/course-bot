// apps/miniapp/src/pages/PausedPage/PausedPage.tsx — экран паузы /paused (lifecycle.paused)
// и защитная проверка допуска к дню DayGuard (miniapp-pause-1 §8).
//
// Логика — components/pause.ts (контроллер с подставными вызовами); здесь только React.
// Ответы и попытки — только в state/ref React: не на устройство, не в лог, не в адрес.
// Навигация — через react-router-dom, как в App.tsx. /returned здесь нет (карточка §13).
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Link, Navigate } from 'react-router-dom';

import {
  getPause,
  newClientOpId,
  postPauseCancel,
  postPauseRequest,
  postPauseResume,
} from '../../api/client.ts';
import {
  PAUSE_TEXT,
  checkDayAccess,
  createPauseController,
  pauseErrorMessage,
  pauseViewModel,
  type DayGate,
  type PauseController,
  type PauseSnapshot,
  type PauseViewModel,
} from '../../components/pause.ts';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const barStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };

// ---- Защитная проверка перед экраном дня ----

/**
 * Один GET /pause при каждом монтировании /day. Пока не завершён — день не монтируется;
 * active → /paused (replace); ошибка или неизвестный status → заглушка и «Повторить».
 * «Помощь» (HelpBar в App.tsx) остаётся доступной: она вне этого компонента.
 */
export function DayGuard({ children }: { children: ReactNode }) {
  const [gate, setGate] = useState<DayGate | 'loading'>('loading');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setGate('loading');
    void checkDayAccess(getPause).then((g) => {
      if (!cancelled) setGate(g);
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (gate === 'loading') {
    return (
      <div className="page" style={pageStyle}>
        <p>{PAUSE_TEXT.dayCheck}</p>
      </div>
    );
  }
  if (gate === 'paused') return <Navigate to="/paused" replace/>;
  if (gate === 'error') {
    return (
      <div className="page" style={pageStyle}>
        <p>{PAUSE_TEXT.dayCheckError}</p>
        <button type="button" onClick={() => setAttempt((n) => n + 1)}>
          {PAUSE_TEXT.retry}
        </button>
      </div>
    );
  }
  return <>{children}</>;
}

// ---- Вид экрана без хуков ----

export interface PausedViewProps {
  vm: PauseViewModel;
  onDays: (days: number) => void;
  onRequest: () => void;
  onCancel: () => void;
  onResume: () => void;
  onRefresh: () => void;
}

/** Готовый экран паузы: бюджет, статус, границы, полосы и ETA, кнопки по статусу. */
export function PausedView({ vm, onDays, onRequest, onCancel, onResume, onRefresh }: PausedViewProps) {
  return (
    <>
      <h1>{PAUSE_TEXT.title}</h1>
      <p>{vm.budgetText}</p>
      {vm.cycleText !== null && <p>{vm.cycleText}</p>}
      <p>{vm.statusText}</p>
      {vm.bounds !== null && (
        <p>
          {PAUSE_TEXT.startsAt}: {vm.bounds.start} · {PAUSE_TEXT.endsAt}: {vm.bounds.end}
        </p>
      )}
      {vm.bars.map((bar) => (
        <div key={bar.label} style={barStyle}>
          <span>{bar.label}</span>
          <progress max={100} value={bar.value}/>
        </div>
      ))}
      {vm.eta !== null && <p>{vm.eta}</p>}
      {vm.refusal !== null && <p>{vm.refusal}</p>}
      {vm.showRequest && vm.dayOptions.length > 0 && (
        <label>
          {PAUSE_TEXT.daysLabel}{' '}
          <select
            value={vm.days}
            disabled={vm.daysLocked}
            onChange={(e) => onDays(Number(e.target.value))}
          >
            {vm.dayOptions.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
      )}
      {vm.showRequest && (
        <button type="button" disabled={!vm.requestEnabled} onClick={onRequest}>
          {vm.requestLabel}
        </button>
      )}
      {vm.showCancel && (
        <button type="button" disabled={!vm.actionsEnabled} onClick={onCancel}>
          {PAUSE_TEXT.cancel}
        </button>
      )}
      {vm.showResume && (
        <button type="button" disabled={!vm.actionsEnabled} onClick={onResume}>
          {PAUSE_TEXT.resume}
        </button>
      )}
      {vm.errorText !== null && <p>{vm.errorText}</p>}
      <button type="button" disabled={!vm.refreshEnabled} onClick={onRefresh}>
        {PAUSE_TEXT.refresh}
      </button>
    </>
  );
}

// ---- Экран ----

export function PausedPage() {
  const [snap, setSnap] = useState<PauseSnapshot | null>(null);
  const ctrlRef = useRef<PauseController | null>(null);

  useEffect(() => {
    const ctrl = createPauseController(
      {
        getPause,
        postPauseRequest,
        postPauseCancel,
        postPauseResume,
        newOpId: newClientOpId,
        now: () => Date.now(),
        setTimer: (fn, ms) => window.setTimeout(fn, ms),
        clearTimer: (h) => window.clearTimeout(h as number),
      },
      setSnap,
    );
    ctrlRef.current = ctrl;
    setSnap(ctrl.snapshot());
    ctrl.start();
    return () => {
      ctrl.dispose();
      ctrlRef.current = null;
    };
  }, []);

  const ctrl = ctrlRef.current;

  if (snap === null || ctrl === null || (snap.load === 'loading' && snap.overview === null)) {
    return (
      <div className="page" style={pageStyle}>
        <p>{PAUSE_TEXT.loading}</p>
      </div>
    );
  }

  if (snap.load === 'error' || snap.overview === null) {
    return (
      <div className="page" style={pageStyle}>
        <p>{pauseErrorMessage(snap.loadError)}</p>
        <button type="button" disabled={snap.busy} onClick={ctrl.refresh}>
          {PAUSE_TEXT.retry}
        </button>
        <Link to="/me">{PAUSE_TEXT.toCard}</Link>
      </div>
    );
  }

  const vm = pauseViewModel(snap, snap.overview);
  return (
    <div className="page" style={pageStyle}>
      <PausedView
        vm={vm}
        onDays={ctrl.setDays}
        onRequest={() => void ctrl.request()}
        onCancel={() => void ctrl.cancel()}
        onResume={() => void ctrl.resume()}
        onRefresh={ctrl.refresh}
      />
      {snap.polling && <p>{PAUSE_TEXT.pending}</p>}
      {vm.showToDay && <Link to="/day">{PAUSE_TEXT.toDay}</Link>}
      <Link to="/me">{PAUSE_TEXT.toCard}</Link>
    </div>
  );
}
