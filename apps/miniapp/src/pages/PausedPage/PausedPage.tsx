// apps/miniapp/src/pages/PausedPage/PausedPage.tsx — экран /paused (miniapp-pause-c3b §7.3, c3b-2).
// Рантайм — из PauseRuntimeContext; null → PAUSE_REOPEN_TEXT без кнопок (хуки вызываются всегда, до return).
// Монтирование: один координатор pause.ts на монтирование, runtime.attach(coord.onOutcome), один reread.
// Размонтирование: detach и coord.dispose(). Повторный вход очереди после GET делает сам координатор.
// Снимок onView живёт только в state React; вид строит pausedView(снимок, сейчас). Исходы операций
// (business, stopped, conflict, нет очереди) разбирает координатор; экран только показывает вид.
// Таймеров два: schedule координатора (серия старта) и включение кнопки «Повторить» после ошибки GET.
// Таймер кнопки GET не делает; по нажатию — снова canRetry и ровно один coord.reread().
// Три POST экран не вызывает: операции ставит координатор (request, cancel, resume).
// Срок формы — runtime.setFormDays (переживает уход в /help); после принятой постановки — null.
// «К экрану дня» → /day; что показать, решает DayGuard свежим GET. Тексты — заглушки [ШТАБ-тех].
import { useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';

import { getPause } from '@/api/client.ts';
import { DayGuardErrorView } from '@/components/DayGuard.tsx';
import { canRetry, retryAtFrom, type DayAccess } from '@/components/dayAccess.ts';
import { dayErrorMessage, wallClock } from '@/components/dayScreen.ts';
import {
  PAUSE_CONFLICT_TEXT,
  PAUSE_REOPEN_TEXT,
  createPauseCoordinator,
  type PauseCoordinator,
  type PauseView,
  type PauseViewError,
} from '@/components/pause.ts';
import { PAUSE_FORM_DAYS_MAX, PAUSE_FORM_DAYS_MIN, PauseRuntimeContext } from '@/components/pauseRuntime.ts';
import { pauseErrorToApi, pausedView, type PauseBar } from '@/components/pausedScreen.ts';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const rowStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };

export const PAUSED_PAGE_TEXT = {
  loading: 'Загрузка…',
  days: 'Срок, дней',
  startPrefix: 'Начало',
  endPrefix: 'Конец',
  statusPrefix: 'Статус паузы',
  request: 'Взять паузу',
  cancel: 'Отменить паузу',
  resume: 'Выйти досрочно',
  toDay: 'К экрану дня',
} as const;

const DAY_OPTIONS: number[] = Array.from(
  { length: PAUSE_FORM_DAYS_MAX - PAUSE_FORM_DAYS_MIN + 1 },
  (_, i) => PAUSE_FORM_DAYS_MIN + i,
);

type ErrorAccess = Extract<DayAccess, { kind: 'error' }>;

interface Snapshot {
  view: PauseView;
  /** Момент получения снимка с текущей ошибкой GET (вход retryAtFrom). */
  errorAt: number;
}

function showDate(iso: string): string {
  const wc = wallClock(iso);
  return wc === null ? iso : `${wc.date} ${wc.time}`;
}

function TextPage({ text }: { text: string }) {
  return (
    <div className="page" style={pageStyle}>
      <p>{text}</p>
    </div>
  );
}

function BarsView({ bars }: { bars: PauseBar[] }) {
  return (
    <>
      {bars.map((bar) => (
        <div key={bar.id} style={rowStyle}>
          <span>{`${bar.label}: ${bar.percent}%`}</span>
          <progress max={100} value={bar.percent}/>
        </div>
      ))}
    </>
  );
}

function ignore(): undefined {
  return undefined;
}

export function PausedPage() {
  const runtime = useContext(PauseRuntimeContext);
  const navigate = useNavigate();
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [days, setDays] = useState<number>(() => runtime?.getFormDays() ?? 1);
  const [readyFor, setReadyFor] = useState<ErrorAccess | null>(null);
  const coordRef = useRef<PauseCoordinator | null>(null);

  useEffect(() => {
    if (runtime === null) return undefined;
    let seenError: PauseViewError | null = null;
    let errorAt = 0;
    const coord = createPauseCoordinator({
      getPause,
      queue: runtime.queue(),
      onView: (view: PauseView) => {
        if (view.error !== seenError) {
          seenError = view.error;
          errorAt = Date.now();
        }
        setSnap({ view, errorAt });
      },
      now: () => Date.now(),
      schedule: (fn, ms) => {
        const id = setTimeout(fn, ms);
        return () => clearTimeout(id);
      },
    });
    coordRef.current = coord;
    const detach = runtime.attach(coord.onOutcome);
    void coord.reread();
    return () => {
      detach();
      coord.dispose();
      if (coordRef.current === coord) coordRef.current = null;
    };
  }, [runtime]);

  const view = snap?.view ?? null;
  const viewError = view !== null && view.data === null && !view.closed ? view.error : null;
  const errorAt = snap?.errorAt ?? 0;
  const loading = view !== null && view.loading;

  const access = useMemo<ErrorAccess | null>(() => {
    if (viewError === null) return null;
    const error = pauseErrorToApi(viewError);
    return { kind: 'error', error, retryAt: retryAtFrom(error, errorAt) };
  }, [viewError, errorAt]);

  useEffect(() => {
    if (access === null || canRetry(access, Date.now())) return undefined;
    const timer = setTimeout(() => setReadyFor(access), Math.max(0, access.retryAt - Date.now()));
    return () => clearTimeout(timer);
  }, [access]);

  const onRetry = useCallback(() => {
    const coord = coordRef.current;
    if (coord === null || access === null || loading || !canRetry(access, Date.now())) return;
    void coord.reread();
  }, [access, loading]);

  const onDaysChange = useCallback(
    (next: number) => {
      setDays(next);
      if (runtime !== null) runtime.setFormDays(next);
    },
    [runtime],
  );

  const onRequest = useCallback(() => {
    const coord = coordRef.current;
    if (coord === null || runtime === null) return;
    void coord
      .request(days)
      .then((accepted: boolean) => {
        if (accepted) runtime.setFormDays(null);
      })
      .catch(ignore);
  }, [days, runtime]);

  const onCancel = useCallback((pauseId: number) => {
    const coord = coordRef.current;
    if (coord !== null) void coord.cancel(pauseId).catch(ignore);
  }, []);

  const onResume = useCallback((pauseId: number) => {
    const coord = coordRef.current;
    if (coord !== null) void coord.resume(pauseId).catch(ignore);
  }, []);

  const toDay = useCallback(() => {
    void navigate('/day');
  }, [navigate]);

  if (runtime === null) return <TextPage text={PAUSE_REOPEN_TEXT}/>;
  if (view === null) return <TextPage text={PAUSED_PAGE_TEXT.loading}/>;

  const model = pausedView(view, Date.now());
  if (model.kind === 'closed' || runtime.sendClosed()) return <TextPage text={PAUSE_CONFLICT_TEXT}/>;

  if (model.kind === 'error' && access !== null) {
    const retryEnabled = !loading && (readyFor === access || canRetry(access, Date.now()));
    return <DayGuardErrorView text={dayErrorMessage(access.error)} retryEnabled={retryEnabled} onRetry={onRetry}/>;
  }
  if (model.kind === 'loading' || model.kind === 'error') return <TextPage text={PAUSED_PAGE_TEXT.loading}/>;

  const data = view.data;
  const pause = data?.pause ?? null;
  const busy = view.busy;

  return (
    <div className="page" style={pageStyle}>
      {model.message !== null && <p>{model.message}</p>}
      {model.kind === 'request' && data !== null && (
        <>
          <label style={rowStyle}>
            <span>{PAUSED_PAGE_TEXT.days}</span>
            <select value={days} disabled={busy} onChange={(e) => onDaysChange(Number(e.target.value))}>
              {DAY_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <p>{`${PAUSED_PAGE_TEXT.startPrefix}: ${data.start_date}`}</p>
          <button type="button" disabled={busy} onClick={onRequest}>
            {PAUSED_PAGE_TEXT.request}
          </button>
        </>
      )}
      {model.kind === 'cancellable' && pause !== null && (
        <>
          <p>{`${PAUSED_PAGE_TEXT.startPrefix}: ${showDate(pause.start_at)}`}</p>
          <p>{`${PAUSED_PAGE_TEXT.endPrefix}: ${showDate(pause.planned_end_at)}`}</p>
          <button type="button" disabled={busy} onClick={() => onCancel(pause.id)}>
            {PAUSED_PAGE_TEXT.cancel}
          </button>
        </>
      )}
      {model.kind === 'active' && pause !== null && (
        <>
          {model.eta !== null && <p>{model.eta}</p>}
          <button type="button" disabled={busy} onClick={() => onResume(pause.id)}>
            {PAUSED_PAGE_TEXT.resume}
          </button>
        </>
      )}
      {model.kind === 'other' && pause !== null && <p>{`${PAUSED_PAGE_TEXT.statusPrefix}: ${pause.status}`}</p>}
      <BarsView bars={model.bars}/>
      <button type="button" onClick={toDay}>
        {PAUSED_PAGE_TEXT.toDay}
      </button>
    </div>
  );
}
