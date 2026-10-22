// apps/miniapp/src/pages/DayPage/DayPage.tsx — экран текущего дня /day (day-screen-a; DM 3.1–3.3, 3.19).
//
// Один GET /miniapp/v1/day/current при монтировании, по «Обновить» и по таймеру refetchDelayMs
// (таймер чистится при размонтировании и при каждом новом ответе). После ответа — /texts/bulk
// только для новых ключей; ошибка текстов экран не ломает (pickText даёт заглушку).
// «Какой экран» — только status, «можно ли нажать» — только buttons_active; окно 04:00–00:00
// клиент не считает; дата и время — из строки сервера (wallClock). Ответы на устройстве не хранятся.
// В day-screen-a блоки только для чтения: кнопок отметок и «Отправить отчёт» нет (day-screen-b).
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';

import { getDayCurrent, postDayTestEnter, postTextsBulk, type DayBlock, type DayCurrent } from '@/api/client.ts';
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

type LoadStatus = 'loading' | 'ready' | 'error';

const MARK_LABEL: Record<'done' | 'not_done', string> = { done: '✅ Выполнил', not_done: '⬜ Не выполнил' };

interface BlockViewProps {
  block: DayBlock;
  t: (key: string) => string;
  helpOpen: boolean;
  onToggleHelp: () => void;
}

function BlockView({ block, t, helpOpen, onToggleHelp }: BlockViewProps) {
  const mark = block.mark === 'done' || block.mark === 'not_done' ? MARK_LABEL[block.mark] : 'не отмечено';
  return (
    <section style={blockStyle}>
      <p>
        {t(block.title_key)}
        {block.critical ? ' ⭐' : null}
      </p>
      <p className="hint">{mark}</p>
      <button type="button" aria-expanded={helpOpen} onClick={onToggleHelp}>
        ❓ Как выполнить?
      </button>
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

  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastViewRef = useRef<DayView | null>(null);
  const sameViewTriesRef = useRef(0);
  const requestedKeysRef = useRef<Set<string>>(new Set());
  // Ref срабатывает синхронно: двойной клик «Тестовый вход» не шлёт два POST.
  const enteringRef = useRef(false);

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

  const blocks = () =>
    (day?.blocks ?? []).map((block) => (
      <BlockView
        key={block.block_id}
        block={block}
        t={t}
        helpOpen={openHelp[block.block_id] === true}
        onToggleHelp={() => setOpenHelp((s) => ({ ...s, [block.block_id]: !s[block.block_id] }))}
      />
    ));

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
          {activeFromLine()}
        </>
      );
      break;
    case 'open':
      body = <>{blocks()}</>;
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
