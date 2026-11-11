// apps/miniapp/src/components/LaterSteps.tsx — онбординг после pid (1e-2; I4 §8; решения «1А», «В2 А», «В3 А»;
// miniapp-i3-1a).
//
// Порядок шагов строгий: offer → form → checkup → rules → finished (заглушка).
// Оплаты (onb.payment) и фото / C5 здесь нет. Оферта — только чтение: в журнал согласий
// ничего не пишется, акцепт — вместе с оплатой (после решения по оплате).
// На каждом шаге — «Назад» и «Шаг N из M» (на первом шаге «Назад» неактивна: pid уже создан,
// вернуться к согласиям нельзя).
// Анкета (шаг form) — экран OnbForm.tsx: ответы уходят на сервер (POST /onboarding/form),
// на устройстве не хранятся (Р-16). Черновик на устройстве — только шаг (drafts.ts:
// привязка к tg_user_id, TTL 24 ч). С form дальше — только действие formDone (анкета на сервере);
// «Далее» на form нет.
// Чек-Ап (шаг checkup) — экран Checkup.tsx (miniapp-i3-1b): ответы только в state React (Р-18, 2А);
// с checkup дальше — только действие checkupDone (Чек-Ап на сервере); «Далее» на checkup нет.
// initialStep — шаг старта, когда черновика нет (App: анкета есть, Чек-Апа нет → checkup);
// найденный незаконченный черновик важнее initialStep.
// finished — экран, а не хранимая метка (returning-2): на экране finished черновик очищается
// (saveDraft), «Перейти к курсу» тоже очищает его (finishDraft). «Пройден ли онбординг»
// решает сервер (GET /onboarding/status в App.tsx), не устройство.
// Тексты — один POST /texts/bulk; ключ в missing → нейтральная заглушка.
// На экране finished — свои согласия (GET /miniapp/v1/consents), только чтение.
import { useEffect, useReducer, useState, type CSSProperties, type ReactNode } from 'react';

import { getConsents, postTextsBulk, type ConsentOut } from '../api/client.ts';
import {
  EMPTY_DRAFT,
  LATER_STEPS,
  finishDraft,
  openDraft,
  saveDraft,
  type Draft,
  type DraftStore,
  type LaterStep,
} from './drafts.ts';
import { Checkup } from './Checkup.tsx';
import { OnbForm } from './OnbForm.tsx';
import { pickText, textsErrorMessage, textsToMap, type TextMap } from './OnboardingFlow.tsx';

// ---- Ключи текстов (онбординг B4.*, юридические legal.*) ----

export const LATER_TEXT_KEYS = {
  offer: 'legal.offer',
  checkup: 'B4.onb_checkup',
  rules: 'B4.onb_rules',
} as const;

export const LATER_TEXT_KEY_LIST: string[] = Object.values(LATER_TEXT_KEYS);

/** Шаги с индикатором прогресса (finished — заглушка, без номера). */
export const PROGRESS_STEPS: readonly LaterStep[] = ['offer', 'form', 'checkup', 'rules'];

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

/** Можно ли нажать «Далее» на текущем шаге: form (только formDone), checkup (только checkupDone) и finished — нет. */
export function canGoNext(draft: Draft): boolean {
  return draft.step !== 'form' && draft.step !== 'checkup' && draft.step !== 'finished';
}

export type LaterAction =
  | { type: 'next' }
  | { type: 'back' }
  | { type: 'formDone' }
  | { type: 'checkupDone' }
  | { type: 'restore'; draft: Draft };

export function laterReducer(state: Draft, action: LaterAction): Draft {
  switch (action.type) {
    case 'next':
      if (!canGoNext(state)) return state;
      return { ...state, step: nextStep(state.step) };
    case 'back':
      return { ...state, step: prevStep(state.step) };
    case 'formDone':
      // Анкета на сервере: только с form → checkup.
      if (state.step !== 'form') return state;
      return { ...state, step: 'checkup' };
    case 'checkupDone':
      // Чек-Ап на сервере: только с checkup → rules.
      if (state.step !== 'checkup') return state;
      return { ...state, step: 'rules' };
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
const progressStyle: CSSProperties = { opacity: 0.7 };

export interface LaterStepViewProps {
  draft: Draft;
  text: string;
  consentsText?: string;
  /** Содержимое шагов form (OnbForm) и checkup (Checkup); на других шагах не используется. */
  body?: ReactNode;
  onAction: (action: LaterAction) => void;
  onFinish: () => void;
}

export function LaterStepView({ draft, text, consentsText, body, onAction, onFinish }: LaterStepViewProps) {
  const back = (
    <button type="button" disabled={draft.step === 'offer'} onClick={() => onAction({ type: 'back' })}>
      Назад
    </button>
  );
  const progress = <p style={progressStyle}>{progressLabel(draft.step)}</p>;
  const next = () => onAction({ type: 'next' });

  // form и checkup: индикатор, экран шага (body) и «Назад»; «Далее» нет.
  if (draft.step === 'form' || draft.step === 'checkup') {
    return (
      <div className="page" style={pageStyle}>
        {progress}
        {body}
        <div style={rowStyle}>{back}</div>
      </div>
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

  // offer, rules — без полей: только текст и кнопки.
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
  if (step === 'form' || step === 'finished') return null;
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
  /** Экран restart анкеты и Чек-Апа (404 / 409 RECONSENT_REQUIRED) → App снова спрашивает status. */
  onRestart: () => void;
  /** Шаг старта, когда черновика нет (по умолчанию offer); незаконченный черновик важнее. */
  initialStep?: LaterStep;
}

export function LaterSteps({ tgUserId, store, onFinish, onRestart, initialStep = 'offer' }: LaterStepsProps) {
  const [draft, dispatch] = useReducer(laterReducer, initialStep, (step: LaterStep): Draft => ({ ...EMPTY_DRAFT, step }));
  const [loaded, setLoaded] = useState(false);
  const [texts, setTexts] = useState<TextMap>({});
  const [textsStatus, setTextsStatus] = useState<TextsStatus>('loading');
  const [textsError, setTextsError] = useState<unknown>(null);
  const [textsAttempt, setTextsAttempt] = useState(0);
  const [consents, setConsents] = useState<ConsentsState>('loading');

  // Открыть черновик: чужой tg_user_id / старше 24 ч / битый / старая метка finished →
  // очистка внутри openDraft.
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

  // Каждое изменение — в черновик (шаг finished → очистка, см. saveDraft).
  // Ошибка записи не мешает пройти шаги.
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
      body={
        draft.step === 'form' ? (
          <OnbForm onDone={() => dispatch({ type: 'formDone' })} onRestart={onRestart}/>
        ) : draft.step === 'checkup' ? (
          <Checkup
            intro={pickText(texts, LATER_TEXT_KEYS.checkup)}
            onDone={() => dispatch({ type: 'checkupDone' })}
            onRestart={onRestart}
          />
        ) : undefined
      }
      onAction={dispatch}
      onFinish={() => {
        void finishDraft(store, tgUserId, Date.now(), onFinish);
      }}
    />
  );
}
