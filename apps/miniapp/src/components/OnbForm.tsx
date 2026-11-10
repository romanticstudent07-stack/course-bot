// apps/miniapp/src/components/OnbForm.tsx — экран onb.form: анкета онбординга (miniapp-i3-1a).
//
// Открытие: GET form/config и GET form параллельно («Загрузка…»); анкета уже отправлена → onDone().
// Поля: город (подсказки с 2 букв, только выбор; «Моего города нет» → 11 кнопок поясов) → tz;
// пол; самочувствие; вес. «Далее» → «всё верно?» [Да] [Исправить] (04 §4.4).
// «Да» шлёт один POST: op_id создаётся при первом нажатии и живёт до 200 или «Исправить»;
// повтор после ошибки — с тем же op_id (D-17); пока запрос идёт, «Да» неактивна.
// Ответы анкеты — только state React: не на устройство, не в лог, не в URL (Р-16).
// cities — один раз из config, только в памяти. Тексты — заглушки (репо публичный).
// Прогресс и «Назад» рисует LaterStepView (LaterSteps.tsx), этот экран — его body.
import { useEffect, useReducer, useRef, useState, type CSSProperties } from 'react';

import { getForm, getFormConfig, newClientOpId, postForm, type FormConfig, type FormGender } from '../api/client.ts';
import {
  INITIAL_FORM,
  buildFormBody,
  canConfirm,
  cityLines,
  formErrorAction,
  formReducer,
  parseWeight,
  suggestCities,
  type FormAction,
  type FormState,
} from './onbForm.ts';
import { errorMessage } from './OnboardingFlow.tsx';

const colStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 12 };
const rowStyle: CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 8 };
const listStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
const smallStyle: CSSProperties = { display: 'block', fontSize: '0.8em', opacity: 0.7 };
const pickedStyle: CSSProperties = { fontWeight: 600 };

export const RESTART_TEXT = 'Заглушка: нужно открыть приложение заново';
export const INVALID_TEXT = 'Заглушка: проверьте ответы';
export const CONFLICT_TEXT = 'Заглушка: не удалось отправить, нажмите «Повторить»';

export function genderLabel(g: FormGender): string {
  return `Заглушка: пол ${g}`;
}

/** Плашка после ошибки POST: текст и кнопка («Повторить» — снова «Да», «Исправить» — к полям). */
export interface FormNotice {
  text: string;
  action: 'retry' | 'edit';
}

// ---- Презентационный компонент (без эффектов и запросов) ----

export interface OnbFormViewProps {
  config: FormConfig;
  state: FormState;
  submitting: boolean;
  notice: FormNotice | null;
  onAction: (action: FormAction) => void;
  onYes: () => void;
}

export function OnbFormView({ config, state, submitting, notice, onAction, onYes }: OnbFormViewProps) {
  if (state.screen === 'confirm') {
    const kg = parseWeight(state.weightText, config.weight);
    const wb = config.wellbeing.find((w) => w.code === state.wellbeing);
    return (
      <div style={colStyle}>
        <p>Заглушка: всё верно?</p>
        <ul>
          <li>Заглушка: город — {state.place}</li>
          <li>{state.gender ? genderLabel(state.gender) : ''}</li>
          <li>Заглушка: самочувствие — {wb ? wb.text : ''}</li>
          <li>Заглушка: вес — {kg === null ? '' : String(kg)}</li>
        </ul>
        {notice ? <p role="alert">{notice.text}</p> : null}
        <div style={rowStyle}>
          <button type="button" onClick={() => onAction({ type: 'edit' })}>
            Исправить
          </button>
          {notice?.action === 'edit' ? null : (
            <button type="button" disabled={submitting} onClick={onYes}>
              {notice?.action === 'retry' ? 'Повторить' : 'Да'}
            </button>
          )}
        </div>
      </div>
    );
  }

  const suggestions = state.tz === null ? suggestCities(config.cities, state.query) : [];
  const weightBad = state.weightText.trim() !== '' && parseWeight(state.weightText, config.weight) === null;

  return (
    <div style={colStyle}>
      <label style={listStyle}>
        <span>Заглушка: ваш город</span>
        <input
          type="text"
          autoComplete="off"
          value={state.query}
          onChange={(e) => onAction({ type: 'setQuery', query: e.target.value })}
        />
      </label>
      {suggestions.length ? (
        <div style={listStyle}>
          {suggestions.map((c) => {
            const [name, region] = cityLines(c);
            const tz = config.timezones[c[2]]?.tz;
            return (
              <button
                key={`${c[0]}|${c[1]}`}
                type="button"
                disabled={!tz}
                onClick={() => {
                  if (tz) onAction({ type: 'pickCity', city: c[0], tz });
                }}
              >
                <span style={{ display: 'block' }}>{name}</span>
                {region ? <span style={smallStyle}>{region}</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
      {state.tz !== null ? <p style={pickedStyle}>✓ {state.place}</p> : null}
      {state.fallbackOpen ? (
        <div style={listStyle}>
          <p>{config.fallback_title}</p>
          <div style={rowStyle}>
            {config.timezones.map((t) => (
              <button
                key={t.tz}
                type="button"
                aria-pressed={state.tz === t.tz}
                style={state.tz === t.tz ? pickedStyle : undefined}
                onClick={() => onAction({ type: 'pickTz', tz: t.tz, place: t.city })}
              >
                {t.city}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <button type="button" onClick={() => onAction({ type: 'openFallback' })}>
          Заглушка: моего города нет
        </button>
      )}

      <div style={rowStyle}>
        {config.genders.map((g) => (
          <button
            key={g}
            type="button"
            aria-pressed={state.gender === g}
            style={state.gender === g ? pickedStyle : undefined}
            onClick={() => onAction({ type: 'setGender', gender: g })}
          >
            {genderLabel(g)}
          </button>
        ))}
      </div>

      <p>{config.wellbeing_question}</p>
      <div style={rowStyle}>
        {config.wellbeing.map((w) => (
          <button
            key={w.code}
            type="button"
            aria-pressed={state.wellbeing === w.code}
            style={state.wellbeing === w.code ? pickedStyle : undefined}
            onClick={() => onAction({ type: 'setWellbeing', code: w.code })}
          >
            {w.text}
          </button>
        ))}
      </div>

      <label style={listStyle}>
        <span>Заглушка: вес, кг</span>
        <input
          type="text"
          inputMode="decimal"
          autoComplete="off"
          value={state.weightText}
          onChange={(e) => onAction({ type: 'setWeight', text: e.target.value })}
        />
      </label>
      {weightBad ? (
        <p role="alert">
          Заглушка: вес от {config.weight.min} до {config.weight.max}
        </p>
      ) : null}

      <div style={rowStyle}>
        <button
          type="button"
          disabled={!canConfirm(state, config.weight)}
          onClick={() => onAction({ type: 'confirm', weight: config.weight })}
        >
          Далее
        </button>
      </div>
    </div>
  );
}

// ---- Контейнер: загрузка, отправка ----

type Load = 'loading' | 'ready' | 'error' | 'restart';

export interface OnbFormProps {
  /** Анкета на сервере (200, уже отправлена или ONBOARDING_FORM_EXISTS) → шаг checkup. */
  onDone: () => void;
  /** «Повторить» на экране restart → App снова спрашивает status. */
  onRestart: () => void;
}

export function OnbForm({ onDone, onRestart }: OnbFormProps) {
  const [load, setLoad] = useState<Load>('loading');
  const [loadError, setLoadError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const [config, setConfig] = useState<FormConfig | null>(null);
  const [state, dispatch] = useReducer(formReducer, INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<FormNotice | null>(null);
  const opIdRef = useRef<string | null>(null);
  const sendingRef = useRef(false);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    let cancelled = false;
    setLoad('loading');
    Promise.all([getFormConfig(), getForm()])
      .then(([cfg, status]) => {
        if (cancelled) return;
        if (status.submitted) {
          onDoneRef.current();
          return;
        }
        setConfig(cfg);
        setLoad('ready');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (formErrorAction(err) === 'restart') {
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

  const onAction = (action: FormAction) => {
    if (action.type === 'edit') {
      opIdRef.current = null;
      setNotice(null);
    }
    dispatch(action);
  };

  const onYes = () => {
    if (sendingRef.current || config === null) return;
    const body = buildFormBody(state, config.weight);
    if (body === null) return;
    if (opIdRef.current === null) opIdRef.current = newClientOpId();
    sendingRef.current = true;
    setSubmitting(true);
    postForm(body, opIdRef.current)
      .then(() => {
        opIdRef.current = null;
        onDoneRef.current();
      })
      .catch((err: unknown) => {
        const next = formErrorAction(err);
        if (next === 'done') {
          onDoneRef.current();
        } else if (next === 'restart') {
          setLoad('restart');
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

  if (load === 'loading') return <p>Загрузка…</p>;

  if (load === 'restart') {
    return (
      <div style={colStyle}>
        <p>{RESTART_TEXT}</p>
        <button type="button" onClick={onRestart}>
          Повторить
        </button>
      </div>
    );
  }

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

  return (
    <OnbFormView
      config={config}
      state={state}
      submitting={submitting}
      notice={notice}
      onAction={onAction}
      onYes={onYes}
    />
  );
}
