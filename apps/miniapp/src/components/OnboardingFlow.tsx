// apps/miniapp/src/components/OnboardingFlow.tsx — онбординг до pid (1e-1b; B-2, D-10, D-14).
//
// Порядок шагов строгий: welcome → age-gate (галочка C0 + дата) → consent (галочка C1)
// → POST first-launch → done. Пока шаг done не пройден и не нажата «Начать», App не
// рендерит ничего другого (block_all_ui_until_checked).
//
// Дата рождения живёт только в состоянии React этого компонента и уходит на сервер
// в теле POST. Больше она никуда не пишется и нигде не выводится. 18+ считает сервер
// (ADD3, Europe/Moscow); клиент проверяет только формат и что такая дата существует.
//
// Тексты — один POST /texts/bulk при монтировании; ключ в missing → нейтральная заглушка.
// Чистые функции и презентационные компоненты экспортируются для vitest (environment node).
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';

import {
  ApiError,
  postFirstLaunch,
  postTextsBulk,
  type ConsentId,
  type FirstLaunchRequest,
  type TextsBulkResponse,
} from '../api/client.ts';

// ---- Ключи текстов (text_registry: онбординг B4.*, согласия legal.*) ----

export const TEXT_KEYS = {
  welcome: 'B4.onb_welcome',
  ageGate: 'B4.onb_age_gate',
  underage: 'B4.onb_age_underage',
  done: 'B4.onb_done',
  consentIntro: 'legal.onb_consent_intro',
  consentC0: 'legal.consent_c0_age_18_plus',
  consentC1: 'legal.consent_c1_pdn',
} as const;

export const ONBOARDING_TEXT_KEYS: string[] = Object.values(TEXT_KEYS);

/** Обязательные до pid согласия, в этом порядке уходят на сервер. */
export const REQUIRED_CONSENTS: ConsentId[] = ['C0', 'C1'];

// ---- Состояние формы ----

export interface OnboardingState {
  /** Галочка C0 «мне есть 18 лет». */
  ageConfirmed: boolean;
  /** Значение input type="date": YYYY-MM-DD или пустая строка. */
  birthDate: string;
  /** Галочка C1 «согласие на обработку ПДн». */
  pdnConsent: boolean;
}

/** Все галочки выключены по умолчанию (D-14: unchecked_by_default). */
export const INITIAL_STATE: OnboardingState = {
  ageConfirmed: false,
  birthDate: '',
  pdnConsent: false,
};

// ---- Чистые функции ----

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Только формат YYYY-MM-DD и реальная дата календаря. Возраст НЕ считаем (это сервер). */
export function isBirthDateFilled(value: string): boolean {
  const m = DATE_RE.exec(value);
  if (!m) return false;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;
  const dt = new Date(Date.UTC(year, month - 1, day));
  return dt.getUTCFullYear() === year && dt.getUTCMonth() === month - 1 && dt.getUTCDate() === day;
}

/** Шаг age-gate: отмечена галочка C0 и заполнена дата. */
export function canContinueAgeGate(state: OnboardingState): boolean {
  return state.ageConfirmed && isBirthDateFilled(state.birthDate);
}

/** Можно отправить first-launch: обе обязательные галочки и дата. */
export function canSubmit(state: OnboardingState): boolean {
  return canContinueAgeGate(state) && state.pdnConsent;
}

/** Тело first-launch. consents — всегда ['C0', 'C1'] в этом порядке. */
export function buildFirstLaunchBody(state: OnboardingState): FirstLaunchRequest {
  return { birth_date: state.birthDate, consents: [...REQUIRED_CONSENTS] };
}

export type ErrorScreen = 'underage' | 'consent' | 'age-gate' | 'error';

/** Куда вести пользователя после ошибки first-launch. */
export function screenAfterError(err: unknown): ErrorScreen {
  if (!(err instanceof ApiError)) return 'error';
  if (err.status === 403 && err.code === 'AGE_GATE_UNDERAGE') return 'underage';
  if (err.status === 422 && (err.code === 'CONSENTS_REQUIRED' || err.code === 'CONSENT_NOT_SUPPORTED')) {
    return 'consent';
  }
  if (err.status === 422 && err.code === 'BIRTH_DATE_IN_FUTURE') return 'age-gate';
  return 'error';
}

/** Понятное сообщение для экрана ошибки (401 / 429 / 503 / сеть / прочее). */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return 'Не удалось подтвердить вход через Telegram. Нажмите «Повторить» или откройте приложение заново.';
    }
    if (err.status === 429) return 'Слишком много попыток подряд. Подождите минуту и нажмите «Повторить».';
    if (err.status === 503) return 'Сервис временно недоступен. Попробуйте чуть позже.';
    return 'Что-то пошло не так. Нажмите «Повторить».';
  }
  return 'Не удалось связаться с сервером. Проверьте интернет и нажмите «Повторить».';
}

export type TextMap = Readonly<Record<string, string>>;

/** Ответ /texts/bulk → словарь key → text. Отсутствующие ключи просто не попадают в словарь. */
export function textsToMap(resp: TextsBulkResponse | null | undefined): TextMap {
  const map: Record<string, string> = {};
  const list = resp && Array.isArray(resp.texts) ? resp.texts : [];
  for (const item of list) {
    if (item && typeof item.key === 'string' && typeof item.text === 'string') map[item.key] = item.text;
  }
  return map;
}

/** Текст по ключу или нейтральная заглушка, если ключ не загружен. */
export function pickText(map: TextMap, key: string): string {
  return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : `[текст не загружен: ${key}]`;
}

// ---- Презентационные компоненты (без эффектов и запросов) ----

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const rowStyle: CSSProperties = { display: 'flex', alignItems: 'flex-start', gap: 8 };
const colStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
const noticeStyle: CSSProperties = { fontWeight: 600 };

export interface AgeGateViewProps {
  text: string;
  c0Label: string;
  state: OnboardingState;
  notice?: string;
  onAgeConfirmedChange: (value: boolean) => void;
  onBirthDateChange: (value: string) => void;
  onContinue: () => void;
}

export function AgeGateView(props: AgeGateViewProps) {
  const disabled = !canContinueAgeGate(props.state);
  return (
    <div className="page" style={pageStyle}>
      <p>{props.text}</p>
      {props.notice ? <p role="alert" style={noticeStyle}>{props.notice}</p> : null}
      <label style={rowStyle}>
        <input
          type="checkbox"
          checked={props.state.ageConfirmed}
          onChange={(e) => props.onAgeConfirmedChange(e.target.checked)}
        />
        <span>{props.c0Label}</span>
      </label>
      <label style={colStyle}>
        <span>Дата рождения</span>
        <input
          type="date"
          autoComplete="off"
          value={props.state.birthDate}
          onChange={(e) => props.onBirthDateChange(e.target.value)}
        />
      </label>
      <button type="button" disabled={disabled} onClick={props.onContinue}>
        Продолжить
      </button>
    </div>
  );
}

export interface ConsentViewProps {
  intro: string;
  c1Label: string;
  state: OnboardingState;
  submitting: boolean;
  notice?: string;
  onPdnConsentChange: (value: boolean) => void;
  onContinue: () => void;
}

export function ConsentView(props: ConsentViewProps) {
  const disabled = props.submitting || !canSubmit(props.state);
  return (
    <div className="page" style={pageStyle}>
      <p>{props.intro}</p>
      {props.notice ? <p role="alert" style={noticeStyle}>{props.notice}</p> : null}
      <label style={rowStyle}>
        <input
          type="checkbox"
          checked={props.state.pdnConsent}
          onChange={(e) => props.onPdnConsentChange(e.target.checked)}
        />
        <span>{props.c1Label}</span>
      </label>
      <button type="button" disabled={disabled} onClick={props.onContinue}>
        {props.submitting ? 'Отправляем…' : 'Продолжить'}
      </button>
    </div>
  );
}

// ---- Контейнер: шаги, тексты, отправка ----

type Step = 'welcome' | 'age-gate' | 'consent' | 'done' | 'underage' | 'error';
type TextsStatus = 'loading' | 'ready' | 'failed';

const NOTICE_CONSENT = 'Чтобы продолжить, отметьте обязательное согласие ниже.';
const NOTICE_FUTURE_DATE = 'Дата рождения не может быть в будущем. Проверьте дату.';

export interface OnboardingFlowProps {
  /** Вызывается, когда пользователь на шаге done нажал «Начать». */
  onComplete: () => void;
}

export function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const [texts, setTexts] = useState<TextMap>({});
  const [textsStatus, setTextsStatus] = useState<TextsStatus>('loading');
  const [textsAttempt, setTextsAttempt] = useState(0);
  const [step, setStep] = useState<Step>('welcome');
  const [state, setState] = useState<OnboardingState>(INITIAL_STATE);
  const [notice, setNotice] = useState<string | undefined>(undefined);
  const [errorText, setErrorText] = useState('');
  const [shortNo, setShortNo] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // Флаг «отправка идёт»: ref срабатывает синхронно, поэтому двойной клик не шлёт два POST.
  const submittingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setTextsStatus('loading');
    postTextsBulk(ONBOARDING_TEXT_KEYS)
      .then((resp) => {
        if (cancelled) return;
        setTexts(textsToMap(resp));
        setTextsStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setTextsStatus('failed');
      });
    return () => {
      cancelled = true;
    };
  }, [textsAttempt]);

  const submit = useCallback(() => {
    if (submittingRef.current || !canSubmit(state)) return;
    submittingRef.current = true;
    setSubmitting(true);
    setNotice(undefined);
    postFirstLaunch(buildFirstLaunchBody(state))
      .then((created) => {
        setShortNo(created.short_no);
        setStep('done');
      })
      .catch((err: unknown) => {
        const next = screenAfterError(err);
        if (next === 'consent') setNotice(NOTICE_CONSENT);
        if (next === 'age-gate') setNotice(NOTICE_FUTURE_DATE);
        if (next === 'error') setErrorText(errorMessage(err));
        setStep(next);
      })
      .finally(() => {
        submittingRef.current = false;
        setSubmitting(false);
      });
  }, [state]);

  const t = (key: string) => pickText(texts, key);

  if (textsStatus === 'loading') {
    return (
      <div className="page" style={pageStyle}>
        <p>Загрузка…</p>
      </div>
    );
  }

  if (textsStatus === 'failed') {
    return (
      <div className="page" style={pageStyle}>
        <p>Не удалось загрузить приложение. Проверьте интернет и нажмите «Повторить».</p>
        <button type="button" onClick={() => setTextsAttempt((n) => n + 1)}>
          Повторить
        </button>
      </div>
    );
  }

  if (step === 'welcome') {
    return (
      <div className="page" style={pageStyle}>
        <p>{t(TEXT_KEYS.welcome)}</p>
        <button type="button" onClick={() => setStep('age-gate')}>
          Продолжить
        </button>
      </div>
    );
  }

  if (step === 'age-gate') {
    return (
      <AgeGateView
        text={t(TEXT_KEYS.ageGate)}
        c0Label={t(TEXT_KEYS.consentC0)}
        state={state}
        notice={notice}
        onAgeConfirmedChange={(value) => setState((s) => ({ ...s, ageConfirmed: value }))}
        onBirthDateChange={(value) => setState((s) => ({ ...s, birthDate: value }))}
        onContinue={() => {
          if (!canContinueAgeGate(state)) return;
          setNotice(undefined);
          setStep('consent');
        }}
      />
    );
  }

  if (step === 'consent') {
    return (
      <ConsentView
        intro={t(TEXT_KEYS.consentIntro)}
        c1Label={t(TEXT_KEYS.consentC1)}
        state={state}
        submitting={submitting}
        notice={notice}
        onPdnConsentChange={(value) => setState((s) => ({ ...s, pdnConsent: value }))}
        onContinue={submit}
      />
    );
  }

  if (step === 'underage') {
    // Р47: дружелюбно, без кнопок «назад»; повтор — только новым запуском приложения.
    return (
      <div className="page" style={pageStyle}>
        <p>{t(TEXT_KEYS.underage)}</p>
        <p>Чтобы попробовать снова, откройте приложение заново.</p>
      </div>
    );
  }

  if (step === 'error') {
    return (
      <div className="page" style={pageStyle}>
        <p>{errorText}</p>
        <button type="button" disabled={submitting} onClick={submit}>
          {submitting ? 'Отправляем…' : 'Повторить'}
        </button>
      </div>
    );
  }

  return (
    <div className="page" style={pageStyle}>
      <p>{t(TEXT_KEYS.done)}</p>
      <p>Ваш номер участника: {shortNo}</p>
      <button type="button" onClick={onComplete}>
        Начать
      </button>
    </div>
  );
}
