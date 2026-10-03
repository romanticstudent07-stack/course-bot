// apps/miniapp/src/components/LaterSteps.tsx — онбординг после pid (1e-2; I4 §8; решения «1А», «В2 А», «В3 А»).
//
// Порядок шагов строгий: offer → email (необязательно) → city → checkup → rules → finished (заглушка).
// Оплаты (onb.payment) и фото / C5 здесь нет. Оферта — только чтение: в журнал согласий
// ничего не пишется, акцепт — вместе с оплатой (после решения по оплате).
// На каждом шаге — «Назад» и «Шаг N из M» (на первом шаге «Назад» неактивна: pid уже создан,
// вернуться к согласиям нельзя).
// Анкета на сервер НЕ уходит: эндпоинта нет — только черновик на устройстве (drafts.ts:
// привязка к tg_user_id, TTL 24 ч, только step / email / city).
// «Перейти к курсу» → в черновике только метка finished (finishDraft, 1e-2b-2).
// Шаги с полями (email, city) — <form> с onSubmit (preventDefault) и основной кнопкой
// type="submit"; Enter при невыполненных условиях ничего не делает.
// Тексты — один POST /texts/bulk; ключ в missing → нейтральная заглушка.
// На экране finished — свои согласия (GET /miniapp/v1/consents), только чтение.
import { useEffect, useReducer, useState, type CSSProperties } from 'react';

import { getConsents, postTextsBulk, type ConsentOut } from '../api/client.ts';
import {
  CITY_OPTIONS,
  EMAIL_MAX_LENGTH,
  EMPTY_DRAFT,
  LATER_STEPS,
  finishDraft,
  openDraft,
  saveDraft,
  type Draft,
  type DraftStore,
  type LaterStep,
} from './drafts.ts';
import { makeSubmitHandler, pickText, textsErrorMessage, textsToMap, type TextMap } from './OnboardingFlow.tsx';

// ---- Ключи текстов (онбординг B4.*, юридические legal.*) ----

export const LATER_TEXT_KEYS = {
  offer: 'legal.offer',
  email: 'B4.onb_email',
  city: 'B4.onb_city',
  checkup: 'B4.onb_checkup',
  rules: 'B4.onb_rules',
} as const;

export const LATER_TEXT_KEY_LIST: string[] = Object.values(LATER_TEXT_KEYS);

/** Шаги с индикатором прогресса (finished — заглушка, без номера). */
export const PROGRESS_STEPS: readonly LaterStep[] = ['offer', 'email', 'city', 'checkup', 'rules'];

// ---- Чистые функции ----

export function stepNumber(step: LaterStep): number | null {
  const i = PROGRESS_STEPS.indexOf(step);
  return i < 0 ? null : i + 1;
}

export function progressLabel(step: LaterStep): string {
  const n = stepNumber(step);
  return n === null ? '' : `Шаг ${n} из ${PROGRESS_STEPS.length}`;
}

export function nextStep(step: LaterStep): LaterStep {
  const i = LATER_STEPS.indexOf(step);
  return LATER_STEPS[Math.min(i + 1, LATER_STEPS.length - 1)];
}

export function prevStep(step: LaterStep): LaterStep {
  const i = LATER_STEPS.indexOf(step);
  return LATER_STEPS[Math.max(i - 1, 0)];
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isEmailValid(email: string): boolean {
  return email.length <= EMAIL_MAX_LENGTH && EMAIL_RE.test(email);
}

/** Email необязателен: пусто — можно дальше; заполнено — только верный адрес. */
export function canContinueEmail(email: string): boolean {
  const value = email.trim();
  return value === '' || isEmailValid(value);
}

function isCityOption(city: string): boolean {
  return (CITY_OPTIONS as readonly string[]).includes(city);
}

/** Можно ли нажать основную кнопку текущего шага. */
export function canGoNext(draft: Draft): boolean {
  if (draft.step === 'email') return canContinueEmail(draft.email);
  if (draft.step === 'city') return isCityOption(draft.city);
  return draft.step !== 'finished';
}

export type LaterAction =
  | { type: 'next' }
  | { type: 'back' }
  | { type: 'setEmail'; email: string }
  | { type: 'skipEmail' }
  | { type: 'setCity'; city: string }
  | { type: 'restore'; draft: Draft };

export function laterReducer(state: Draft, action: LaterAction): Draft {
  switch (action.type) {
    case 'next':
      if (!canGoNext(state)) return state;
      if (state.step === 'email') return { ...state, email: state.email.trim(), step: nextStep(state.step) };
      return { ...state, step: nextStep(state.step) };
    case 'back':
      return { ...state, step: prevStep(state.step) };
    case 'setEmail':
      if (state.step !== 'email') return state;
      return { ...state, email: action.email.slice(0, EMAIL_MAX_LENGTH) };
    case 'skipEmail':
      if (state.step !== 'email') return state;
      return { ...state, email: '', step: 'city' };
    case 'setCity':
      if (state.step !== 'city' || !isCityOption(action.city)) return state;
      return { ...state, city: action.city };
    case 'restore':
      return action.draft;
    default:
      return state;
  }
}

/** Действующие согласия (последнее событие — give). */
export function activeConsentIds(list: readonly ConsentOut[]): string[] {
  return list.filter((c) => c.revoked_at === null).map((c) => c.id).sort();
}

export type ConsentsState = ConsentOut[] | 'loading' | 'failed';

export function consentsLabel(value: ConsentsState): string {
  if (value === 'loading') return 'Ваши согласия: загрузка…';
  if (value === 'failed') return 'Ваши согласия: не удалось загрузить.';
  const ids = activeConsentIds(value);
  return ids.length ? `Ваши согласия: ${ids.join(', ')}` : 'Ваши согласия: нет';
}

// ---- Презентационный компонент (без эффектов и запросов) ----

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const rowStyle: CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 8 };
const colStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
const progressStyle: CSSProperties = { opacity: 0.7 };
const noticeStyle: CSSProperties = { fontWeight: 600 };

export interface LaterStepViewProps {
  draft: Draft;
  text: string;
  consentsText?: string;
  onAction: (action: LaterAction) => void;
  onFinish: () => void;
}

export function LaterStepView({ draft, text, consentsText, onAction, onFinish }: LaterStepViewProps) {
  const back = (
    <button type="button" disabled={draft.step === 'offer'} onClick={() => onAction({ type: 'back' })}>
      Назад
    </button>
  );
  const progress = <p style={progressStyle}>{progressLabel(draft.step)}</p>;
  const next = () => onAction({ type: 'next' });
  const enabled = canGoNext(draft);

  if (draft.step === 'email') {
    const showNotice = !enabled;
    return (
      <form className="page" style={pageStyle} onSubmit={makeSubmitHandler(enabled, next)}>
        {progress}
        <p>{text}</p>
        <label style={colStyle}>
          <span>Email (необязательно)</span>
          <input
            type="email"
            inputMode="email"
            autoComplete="email"
            maxLength={EMAIL_MAX_LENGTH}
            value={draft.email}
            onChange={(e) => onAction({ type: 'setEmail', email: e.target.value })}
          />
        </label>
        {showNotice ? (
          <p role="alert" style={noticeStyle}>Проверьте адрес или нажмите «Пропустить».</p>
        ) : null}
        <div style={rowStyle}>
          {back}
          <button type="button" onClick={() => onAction({ type: 'skipEmail' })}>
            Пропустить
          </button>
          <button type="submit" disabled={!enabled}>
            Далее
          </button>
        </div>
      </form>
    );
  }

  if (draft.step === 'city') {
    return (
      <form className="page" style={pageStyle} onSubmit={makeSubmitHandler(enabled, next)}>
        {progress}
        <p>{text}</p>
        <div style={rowStyle}>
          {CITY_OPTIONS.map((city) => (
            <button
              key={city}
              type="button"
              aria-pressed={draft.city === city}
              style={draft.city === city ? noticeStyle : undefined}
              onClick={() => onAction({ type: 'setCity', city })}
            >
              {draft.city === city ? `✓ ${city}` : city}
            </button>
          ))}
        </div>
        <div style={rowStyle}>
          {back}
          <button type="submit" disabled={!enabled}>
            Далее
          </button>
        </div>
      </form>
    );
  }

  if (draft.step === 'finished') {
    return (
      <div className="page" style={pageStyle}>
        <p>Анкета заполнена. Дальше — курс (экран-заглушка).</p>
        {consentsText ? <p>{consentsText}</p> : null}
        <div style={rowStyle}>
          {back}
          <button type="button" onClick={onFinish}>
            Перейти к курсу
          </button>
        </div>
      </div>
    );
  }

  // offer, checkup, rules — без полей: только текст и кнопки.
  return (
    <div className="page" style={pageStyle}>
      {progress}
      <p>{text}</p>
      <div style={rowStyle}>
        {back}
        <button type="button" onClick={next}>
          {draft.step === 'rules' ? 'Ознакомлен' : 'Далее'}
        </button>
      </div>
    </div>
  );
}

export function textKeyFor(step: LaterStep): string | null {
  if (step === 'finished') return null;
  return LATER_TEXT_KEYS[step];
}

// ---- Контейнер: черновик, тексты, согласия ----

type TextsStatus = 'loading' | 'ready' | 'failed';

export interface LaterStepsProps {
  /** tg_user_id из initData — только для привязки черновика (решения принимает сервер). */
  tgUserId: number | null;
  store: DraftStore;
  /** «Перейти к курсу» на экране-заглушке. */
  onFinish: () => void;
}

export function LaterSteps({ tgUserId, store, onFinish }: LaterStepsProps) {
  const [draft, dispatch] = useReducer(laterReducer, EMPTY_DRAFT);
  const [loaded, setLoaded] = useState(false);
  const [texts, setTexts] = useState<TextMap>({});
  const [textsStatus, setTextsStatus] = useState<TextsStatus>('loading');
  const [textsError, setTextsError] = useState<unknown>(null);
  const [textsAttempt, setTextsAttempt] = useState(0);
  const [consents, setConsents] = useState<ConsentsState>('loading');

  // Открыть черновик: чужой tg_user_id / старше 24 ч / битый → очистка внутри openDraft.
  useEffect(() => {
    let cancelled = false;
    openDraft(store, tgUserId, Date.now())
      .catch(() => null)
      .then((found) => {
        if (cancelled) return;
        if (found) dispatch({ type: 'restore', draft: found });
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [store, tgUserId]);

  // Каждое изменение — в черновик. Ошибка записи не мешает пройти шаги.
  useEffect(() => {
    if (!loaded) return;
    saveDraft(store, tgUserId, draft, Date.now()).catch(() => undefined);
  }, [loaded, draft, store, tgUserId]);

  useEffect(() => {
    let cancelled = false;
    setTextsStatus('loading');
    postTextsBulk(LATER_TEXT_KEY_LIST)
      .then((resp) => {
        if (cancelled) return;
        setTexts(textsToMap(resp));
        setTextsStatus('ready');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTextsError(err);
        setTextsStatus('failed');
      });
    return () => {
      cancelled = true;
    };
  }, [textsAttempt]);

  useEffect(() => {
    if (draft.step !== 'finished') return;
    let cancelled = false;
    setConsents('loading');
    getConsents()
      .then((list) => {
        if (!cancelled) setConsents(list);
      })
      .catch(() => {
        if (!cancelled) setConsents('failed');
      });
    return () => {
      cancelled = true;
    };
  }, [draft.step]);

  if (!loaded || textsStatus === 'loading') {
    return (
      <div className="page" style={pageStyle}>
        <p>Загрузка…</p>
      </div>
    );
  }

  if (textsStatus === 'failed') {
    return (
      <div className="page" style={pageStyle}>
        <p>{textsErrorMessage(textsError)}</p>
        <button type="button" onClick={() => setTextsAttempt((n) => n + 1)}>
          Повторить
        </button>
      </div>
    );
  }

  const key = textKeyFor(draft.step);
  return (
    <LaterStepView
      draft={draft}
      text={key ? pickText(texts, key) : ''}
      consentsText={draft.step === 'finished' ? consentsLabel(consents) : undefined}
      onAction={dispatch}
      onFinish={() => {
        void finishDraft(store, tgUserId, Date.now(), onFinish);
      }}
    />
  );
}
