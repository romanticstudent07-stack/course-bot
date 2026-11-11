// apps/miniapp/src/components/Checkup.tsx — экран onb.checkup: Чек-Ап онбординга (miniapp-i3-1b).
//
// Открытие: GET checkup/config и GET checkup/status параллельно («Загрузка…»); Чек-Ап уже пройден
// (решает сервер, 1А) → onDone(). Вопросы по одному: заголовок блока, «Вопрос N из M», кнопки
// scale.min…scale.max (0–3), ввода с клавиатуры нет (05 Fail-safe). «Исправить» → предыдущий вопрос,
// прежний ответ отмечен. После последнего — «ответы готовы» [Отправить] [Исправить].
// «Отправить» шлёт один POST: op_id создаётся при первом нажатии и живёт до 200 или «Исправить»;
// повтор после ошибки — с тем же op_id (D-17); пока запрос идёт, кнопка неактивна.
// Итог — зона и дисклеймер, балла нет. Ответы и зона — только state React: не на устройство,
// не в лог, не в URL (Р-18, 2А): закрыл приложение → опрос с вопроса 1.
// Прогресс шагов и «Назад» рисует LaterStepView (LaterSteps.tsx), этот экран — его body.
import { useEffect, useReducer, useRef, useState, type CSSProperties } from 'react';

import {
  getCheckupConfig,
  getCheckupStatus,
  newClientOpId,
  postCheckupSubmit,
  type CheckupConfig,
} from '../api/client.ts';
import {
  blockTitle,
  buildSubmitBody,
  checkupErrorAction,
  checkupReducer,
  initialCheckup,
  questionLabel,
  scaleValues,
  zoneView,
  type CheckupState,
  type ZoneView,
} from './checkup.ts';
import { errorMessage } from './OnboardingFlow.tsx';

const colStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 12 };
const rowStyle: CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 8 };
const mutedStyle: CSSProperties = { opacity: 0.7 };
const pickedStyle: CSSProperties = { fontWeight: 600 };

export const RESTART_TEXT = 'Заглушка: нужно открыть приложение заново';
export const READY_TEXT = 'Заглушка: ответы готовы';
export const INVALID_TEXT = 'Заглушка: проверьте ответы';
export const CONFLICT_TEXT = 'Заглушка: не удалось отправить, нажмите «Повторить»';

/** Плашка после ошибки POST: «Повторить» — снова «Отправить», «Исправить» — к вопросам. */
export interface CheckupNotice {
  text: string;
  action: 'retry' | 'edit';
}

// ---- Презентационный компонент вопроса (без эффектов и запросов) ----

export interface CheckupQuestionViewProps {
  config: CheckupConfig;
  state: CheckupState;
  onAnswer: (index: number, value: number) => void;
  onFix: () => void;
}

export function CheckupQuestionView({ config, state, onAnswer, onFix }: CheckupQuestionViewProps) {
  const question = config.questions[state.index];
  if (!question) return null;
  const picked = state.answers[state.index] ?? null;
  const index = state.index;
  return (
    <div style={colStyle}>
      <p style={pickedStyle}>{blockTitle(config, question)}</p>
      <p style={mutedStyle}>{questionLabel(index, state.total)}</p>
      <p>{question.text}</p>
      <div style={rowStyle}>
        {scaleValues(config.scale).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={picked === v}
            style={picked === v ? pickedStyle : undefined}
            onClick={() => onAnswer(index, v)}
          >
            {picked === v ? `✓ ${v}` : String(v)}
          </button>
        ))}
      </div>
      {index > 0 ? (
        <div style={rowStyle}>
          <button type="button" onClick={onFix}>
            Исправить
          </button>
        </div>
      ) : null}
    </div>
  );
}

// ---- Опрос: вопросы, отправка, итог (монтируется после загрузки config) ----

interface CheckupRunProps {
  config: CheckupConfig;
  intro: string;
  onDone: () => void;
  onRestart: () => void;
}

function CheckupRun({ config, intro, onDone, onRestart }: CheckupRunProps) {
  const [state, dispatch] = useReducer(checkupReducer, config.questions.length, initialCheckup);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<CheckupNotice | null>(null);
  const [result, setResult] = useState<ZoneView | null>(null);
  const [restart, setRestart] = useState(false);
  const opIdRef = useRef<string | null>(null);
  const sendingRef = useRef(false);

  const onFix = () => {
    // Тело изменится → новый op_id при следующей отправке.
    opIdRef.current = null;
    setNotice(null);
    dispatch({ type: 'fix' });
  };

  const onSend = () => {
    if (sendingRef.current) return;
    const body = buildSubmitBody(state, config.scale);
    if (body === null) return;
    if (opIdRef.current === null) opIdRef.current = newClientOpId();
    sendingRef.current = true;
    setSubmitting(true);
    postCheckupSubmit(body, opIdRef.current)
      .then((resp) => {
        opIdRef.current = null;
        setNotice(null);
        setResult(zoneView(config, resp.zone));
      })
      .catch((err: unknown) => {
        const next = checkupErrorAction(err);
        if (next === 'done') {
          onDone();
        } else if (next === 'restart') {
          setRestart(true);
        } else if (next === 'conflict') {
          opIdRef.current = newClientOpId();
          setNotice({ text: CONFLICT_TEXT, action: 'retry' });
        } else if (next === 'invalid') {
          setNotice({ text: INVALID_TEXT, action: 'edit' });
        } else {
          setNotice({ text: errorMessage(err), action: 'retry' });
        }
      })
      .finally(() => {
        sendingRef.current = false;
        setSubmitting(false);
      });
  };

  if (restart) return <RestartView onRestart={onRestart}/>;

  if (result !== null) {
    return (
      <div style={colStyle}>
        <p style={pickedStyle}>{result.title}</p>
        {result.text ? <p>{result.text}</p> : null}
        <p style={mutedStyle}>{config.disclaimer}</p>
        <div style={rowStyle}>
          <button type="button" onClick={onDone}>
            Далее
          </button>
        </div>
      </div>
    );
  }

  if (state.index >= state.total) {
    return (
      <div style={colStyle}>
        <p>{READY_TEXT}</p>
        {notice ? <p role="alert">{notice.text}</p> : null}
        <div style={rowStyle}>
          {notice?.action === 'edit' ? null : (
            <button type="button" disabled={submitting} onClick={onSend}>
              {notice?.action === 'retry' ? 'Повторить' : 'Отправить'}
            </button>
          )}
          <button type="button" disabled={submitting} onClick={onFix}>
            Исправить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={colStyle}>
      {intro ? <p>{intro}</p> : null}
      <CheckupQuestionView
        config={config}
        state={state}
        onAnswer={(index, value) => dispatch({ type: 'answer', index, value })}
        onFix={onFix}
      />
    </div>
  );
}

function RestartView({ onRestart }: { onRestart: () => void }) {
  return (
    <div style={colStyle}>
      <p>{RESTART_TEXT}</p>
      <button type="button" onClick={onRestart}>
        Повторить
      </button>
    </div>
  );
}

// ---- Контейнер: загрузка config и status ----

type Load = 'loading' | 'ready' | 'error' | 'restart';

export interface CheckupProps {
  /** Текст шага (B4.onb_checkup). */
  intro: string;
  /** Чек-Ап на сервере (уже пройден, 200 + «Далее» или CHECKUP_EXISTS) → шаг rules. */
  onDone: () => void;
  /** «Повторить» на экране restart → App снова спрашивает status. */
  onRestart: () => void;
}

export function Checkup({ intro, onDone, onRestart }: CheckupProps) {
  const [load, setLoad] = useState<Load>('loading');
  const [loadError, setLoadError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const [config, setConfig] = useState<CheckupConfig | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    let cancelled = false;
    setLoad('loading');
    Promise.all([getCheckupConfig(), getCheckupStatus()])
      .then(([cfg, status]) => {
        if (cancelled) return;
        if (status.completed) {
          onDoneRef.current();
          return;
        }
        setConfig(cfg);
        setLoad('ready');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (checkupErrorAction(err) === 'restart') {
          setLoad('restart');
          return;
        }
        setLoadError(err);
        setLoad('error');
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (load === 'loading') return <p>Загрузка…</p>;

  if (load === 'restart') return <RestartView onRestart={onRestart}/>;

  if (load === 'error' || config === null) {
    return (
      <div style={colStyle}>
        <p>{errorMessage(loadError)}</p>
        <button type="button" onClick={() => setAttempt((n) => n + 1)}>
          Повторить
        </button>
      </div>
    );
  }

  return <CheckupRun config={config} intro={intro} onDone={() => onDoneRef.current()} onRestart={onRestart}/>;
}
