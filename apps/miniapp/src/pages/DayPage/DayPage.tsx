// apps/miniapp/src/pages/DayPage/DayPage.tsx — экран текущего дня /day (day-screen-a; DM 3.1–3.3, 3.19).
//
// Один GET /miniapp/v1/day/current при монтировании, по «Обновить» и по таймеру refetchDelayMs
// (таймер чистится при размонтировании и при каждом новом ответе). После ответа — /texts/bulk
// только для новых ключей; ошибка текстов экран не ломает (pickText даёт заглушку).
// «Какой экран» — только status, «можно ли нажать» — только buttons_active; окно 04:00–00:00
// клиент не считает; дата и время — из строки сервера (wallClock). Ответы на устройстве не хранятся.
// day-screen-b: под блоком «Выполнил» / «Не выполнил» (PUT /day/marks, сразу на сервер — DM 3.4),
// «Отправить отчёт» (POST /day/report/submit) — когда отмечены все блоки (DM 3.3). Один X-Client-Op-Id
// на то же тело: повтор после ошибки — с ним же (D-17). «Отправлено» — только после 200 (DM 3.11);
// после первого нажатия кнопка гаснет (DM 3.10). Вердикт экран не показывает (DM 3.19).
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';

import {
  getDayCurrent,
  newClientOpId,
  postDayReport,
  postDayTestEnter,
  postTextsBulk,
  putDayMark,
  type DayBlock,
  type DayCurrent,
  type DayMarkValue,
} from '@/api/client.ts';
import {
  actionMessage,
  canPressMark,
  canSendReport,
  markErrorAction,
  markLabels,
  marksFromDay,
  reportBody,
  reuseOpId,
  submitErrorAction,
  type LocalMarks,
  type OpRef,
} from '@/components/dayMarks.ts';
import {
  DAY_TEXT_KEYS,
  REOPEN_MESSAGE,
  dayErrorMessage,
  dayTextKeys,
  dayView,
  refetchDelayMs,
  testEnterAction,
  wallClock,
  type DayView,
} from '@/components/dayScreen.ts';
import { errorMessage, pickText, textsToMap, type TextMap } from '@/components/OnboardingFlow.tsx';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const blockStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 8 };
const noticeStyle: CSSProperties = { fontWeight: 600 };
const rowStyle: CSSProperties = { display: 'flex', gap: 8 };

type LoadStatus = 'loading' | 'ready' | 'error';

interface BlockViewProps {
  block: DayBlock;
  t: (key: string) => string;
  helpOpen: boolean;
  onToggleHelp: () => void;
  mark: DayMarkValue | undefined;
  marksEnabled: boolean;
  onMark: (value: DayMarkValue) => void;
}

function BlockView({ block, t, helpOpen, onToggleHelp, mark, marksEnabled, onMark }: BlockViewProps) {
  const labels = markLabels(mark);
  return (
    <section style={blockStyle}>
      <p>
        {t(block.title_key)}
        {block.critical ? ' ⭐' : null}
      </p>
      <div style={rowStyle}>
        <button type="button" aria-pressed={mark === 'done'} disabled={!marksEnabled} onClick={() => onMark('done')}>
          {labels.done}
        </button>
        <button
          type="button"
          aria-pressed={mark === 'not_done'}
          disabled={!marksEnabled}
          onClick={() => onMark('not_done')}
        >
          {labels.notDone}
        </button>
      </div>
      <div style={rowStyle}>
        <button type="button" aria-expanded={helpOpen} onClick={onToggleHelp}>
          ❓ Как выполнить?
        </button>
      </div>
      {helpOpen ? <p>{t(block.help_key)}</p> : null}
    </section>
  );
}

export function DayPage() {
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [day, setDay] = useState<DayCurrent | null>(null);
  const [view, setView] = useState<DayView>('unknown');
  const [loadError, setLoadError] = useState<unknown>(null);
  const [texts, setTexts] = useState<TextMap>({});
  const [openHelp, setOpenHelp] = useState<Record<string, boolean>>({});
  const [entering, setEntering] = useState(false);
  const [notice, setNotice] = useState('');
  // Отметки — из каждого GET (сервер — источник правды) и из ответа PUT 200; на устройстве не хранятся.
  const [marks, setMarks] = useState<LocalMarks>({});
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastViewRef = useRef<DayView | null>(null);
  const sameViewTriesRef = useRef(0);
  const requestedKeysRef = useRef<Set<string>>(new Set());
  // Ref срабатывает синхронно: двойной клик «Тестовый вход» не шлёт два POST.
  const enteringRef = useRef(false);
  // Один PUT на блок за раз; ref — синхронно, двойной клик не шлёт два запроса.
  const pendingRef = useRef<Set<string>>(new Set());
  // Двойной клик «Отправить отчёт» не шлёт два POST (DM 3.10).
  const sendingRef = useRef(false);
  // X-Client-Op-Id текущей попытки отчёта: повтор того же тела — с тем же id (D-17).
  const opRef = useRef<OpRef | null>(null);
  // view и day_started_at на момент успешной отправки: sent держится, пока GET их не сменит.
  const sentFromRef = useRef<{ view: DayView; started: string | null } | null>(null);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const loadTexts = useCallback((resp: DayCurrent) => {
    const fresh = dayTextKeys(resp).filter((k) => !requestedKeysRef.current.has(k));
    if (fresh.length === 0) return;
    for (const k of fresh) requestedKeysRef.current.add(k);
    postTextsBulk(fresh)
      .then((r) => {
        if (!mountedRef.current) return;
        const add = textsToMap(r);
        setTexts((prev) => ({ ...prev, ...add }));
      })
      .catch(() => {
        // Экран не ломаем: pickText покажет заглушку; при следующем ответе ключи запросятся снова.
        for (const k of fresh) requestedKeysRef.current.delete(k);
      });
  }, []);

  // Один GET. showLoading — только при монтировании, «Обновить» и «Повторить»; по таймеру — тихо.
  const load = useCallback(
    (showLoading: boolean) => {
      clearTimer();
      const id = ++requestIdRef.current;
      if (showLoading) setStatus('loading');
      getDayCurrent()
        .then((resp: DayCurrent) => {
          if (!mountedRef.current || id !== requestIdRef.current) return;
          const next = dayView(resp);
          sameViewTriesRef.current = lastViewRef.current === next ? sameViewTriesRef.current + 1 : 0;
          lastViewRef.current = next;
          setDay(resp);
          setView(next);
          setMarks(marksFromDay(resp));
          const from = sentFromRef.current;
          if (from && (from.view !== next || from.started !== (resp.day_started_at ?? null))) {
            sentFromRef.current = null;
            setSent(false);
          }
          setLoadError(null);
          setStatus('ready');
          if (next !== 'unknown') loadTexts(resp);
          const delay = refetchDelayMs(resp, Date.now(), sameViewTriesRef.current);
          if (delay !== null) timerRef.current = setTimeout(() => load(false), delay);
        })
        .catch((err: unknown) => {
          if (!mountedRef.current || id !== requestIdRef.current) return;
          setLoadError(err);
          setStatus('error');
        });
    },
    [loadTexts],
  );

  useEffect(() => {
    mountedRef.current = true;
    load(true);
    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [load]);

  const refresh = () => {
    setNotice('');
    load(true);
  };

  const testEnter = () => {
    if (enteringRef.current) return;
    enteringRef.current = true;
    setEntering(true);
    setNotice('');
    const finish = () => {
      enteringRef.current = false;
      if (mountedRef.current) setEntering(false);
    };
    const attempt = (retried: boolean) => {
      postDayTestEnter()
        .then(() => {
          finish();
          if (mountedRef.current) load(true);
        })
        .catch((err: unknown) => {
          if (!mountedRef.current) return;
          const action = testEnterAction(err);
          if (action === 'retry_1s' && !retried) {
            setTimeout(() => {
              if (mountedRef.current) attempt(true);
            }, 1000);
            return;
          }
          finish();
          if (action === 'refetch') load(true);
          else if (action === 'reopen') setNotice(REOPEN_MESSAGE);
          else setNotice(errorMessage(err));
        });
    };
    attempt(false);
  };

  const markPress = (blockId: string, value: DayMarkValue) => {
    if (!canPressMark(view, day, { sending: sendingRef.current, sent })) return;
    if (marks[blockId] === value || pendingRef.current.has(blockId)) return;
    pendingRef.current.add(blockId);
    setPending(new Set(pendingRef.current));
    setNotice('');
    putDayMark({ block_id: blockId, value })
      .then((r) => {
        if (!mountedRef.current) return;
        setMarks((m) => ({ ...m, [r.block_id]: r.value }));
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return;
        // Отметка остаётся прежней: ложного успеха нет (DM 3.11).
        setNotice(actionMessage(err, 'mark'));
        if (markErrorAction(err) === 'refetch') load(false);
      })
      .finally(() => {
        pendingRef.current.delete(blockId);
        if (mountedRef.current) setPending(new Set(pendingRef.current));
      });
  };

  const sendReport = () => {
    if (sendingRef.current || pendingRef.current.size > 0) return;
    if (!canSendReport(view, day, { sending: false, sent }, marks)) return;
    const blockList = day?.blocks ?? [];
    sendingRef.current = true;
    setSending(true);
    setNotice('');
    const body = reportBody(blockList, marks);
    const op = reuseOpId(opRef.current, body, newClientOpId);
    opRef.current = op;
    const sentFrom = { view, started: day?.day_started_at ?? null };
    postDayReport(body, op.opId)
      .then(() => {
        // Только после 200: кнопка остаётся погашенной, вердикт не показываем.
        opRef.current = null;
        if (!mountedRef.current) return;
        sentFromRef.current = sentFrom;
        setSent(true);
        load(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return;
        setNotice(actionMessage(err, 'report'));
        const action = submitErrorAction(err);
        if (action === 'new_op_refetch') {
          opRef.current = null;
          load(false);
        } else if (action === 'refetch') {
          load(false);
        }
        // 'retry' — кнопка снова активна, повтор уйдёт с тем же opId.
      })
      .finally(() => {
        sendingRef.current = false;
        if (mountedRef.current) setSending(false);
      });
  };

  const t = (key: string) => pickText(texts, key);

  if (status === 'loading') {
    return (
      <div className="page" style={pageStyle}>
        <p>Загрузка…</p>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="page" style={pageStyle}>
        <p>{dayErrorMessage(loadError)}</p>
        <button type="button" onClick={refresh}>
          Повторить
        </button>
      </div>
    );
  }

  if (view === 'unknown') {
    return (
      <div className="page" style={pageStyle}>
        <p>Что-то пошло не так.</p>
        <button type="button" onClick={refresh}>
          Повторить
        </button>
      </div>
    );
  }

  const activeFromLine = () => {
    const wc = wallClock(day?.active_from);
    return (
      <p>
        {t(DAY_TEXT_KEYS.activeFromHint)}
        {wc ? ` ${wc.date} в ${wc.time}` : null}
      </p>
    );
  };

  // В not_active кнопки видны, но disabled (DM 3.1); в closed, queued и submitted блоков с кнопками нет.
  const marksAllowed = canPressMark(view, day, { sending, sent });
  const blocks = () =>
    (day?.blocks ?? []).map((block) => (
      <BlockView
        key={block.block_id}
        block={block}
        t={t}
        helpOpen={openHelp[block.block_id] === true}
        onToggleHelp={() => setOpenHelp((s) => ({ ...s, [block.block_id]: !s[block.block_id] }))}
        mark={marks[block.block_id]}
        marksEnabled={marksAllowed && !pending.has(block.block_id)}
        onMark={(value) => markPress(block.block_id, value)}
      />
    ));

  const reportRow = () => (
    <div style={rowStyle}>
      <button
        type="button"
        disabled={!canSendReport(view, day, { sending, sent }, marks) || pending.size > 0}
        onClick={sendReport}
      >
        {sending ? 'Отправляем…' : 'Отправить отчёт'}
      </button>
    </div>
  );

  let body;
  switch (view) {
    case 'test_entry':
      body = (
        <>
          <p>День ещё не начат.</p>
          <button type="button" disabled={entering} onClick={testEnter}>
            {entering ? 'Отправляем…' : 'Тестовый вход'}
          </button>
        </>
      );
      break;
    case 'not_started':
      body = <p>День ещё не начат.</p>;
      break;
    case 'entering':
      body = <p>Готовим день…</p>;
      break;
    case 'not_active':
      body = (
        <>
          {blocks()}
          {reportRow()}
          {activeFromLine()}
        </>
      );
      break;
    case 'open':
      body = (
        <>
          {blocks()}
          {reportRow()}
        </>
      );
      break;
    case 'submitted':
      body = <p>{t(DAY_TEXT_KEYS.queueWait)}</p>;
      break;
    case 'queued':
      body = (
        <>
          <p>{t(DAY_TEXT_KEYS.queueWait)}</p>
          {activeFromLine()}
        </>
      );
      break;
    case 'closed':
      body = <p>{t(DAY_TEXT_KEYS.closedHint)}</p>;
      break;
  }

  return (
    <div className="page" style={pageStyle}>
      {body}
      {notice ? <p role="alert" style={noticeStyle}>{notice}</p> : null}
      <button type="button" onClick={refresh}>
        Обновить
      </button>
    </div>
  );
}
