// apps/miniapp/src/components/SupportScreen.tsx — экран «Помощь» (miniapp-sup-1, Р-19).
//
// Шаги: тема (8 кнопок) → вопрос (поле и «Отправить») → «Вопрос отправлен.».
// Названия тем — заглушки самого Р-19, без text_registry; заменить до показа участникам курса.
// Черновик (тема и текст) — только через drafts.ts: openSupportDraft при монтировании,
// saveSupportDraft на каждое изменение темы или текста, clearSupportDraft после 201.
// Сам экран на устройство не пишет. Текст вопроса — только тело POST: не в лог, не в адрес, не в query.
// Проверка текста — как на сервере: минимум 2 знака после trim, максимум 2000 по сырому тексту,
// счёт по кодовым точкам; символ NUL нельзя. Отправляется текст как введён.
// X-Client-Op-Id — один на попытку: смена темы или текста сбрасывает его, ошибка — нет
// (повтор уходит с тем же id), 201 — сбрасывает.
// Ошибки — supportErrorView: 404 PARTICIPANT_NOT_FOUND и 409 RECONSENT_REQUIRED → «Повторить» →
// onRestart (черновик не трогаем); остальное — текст под полем; таймера нет.
import { useEffect, useRef, useState, type CSSProperties } from 'react';

import {
  ApiError,
  newClientOpId,
  postSupportQuestion,
  type SupportQuestionBody,
  type SupportTopicCode,
} from '../api/client.ts';
import {
  EMPTY_SUPPORT_DRAFT,
  clearSupportDraft,
  openSupportDraft,
  saveSupportDraft,
  type SupportDraft,
  type SupportDraftStore,
} from './drafts.ts';

export interface SupportTopic {
  code: SupportTopicCode;
  label: string;
}

/** Порядок и коды = SUPPORT_TOPIC_CODES (drafts.ts). Подписи — заглушки Р-19. */
export const SUPPORT_TOPICS: readonly SupportTopic[] = [
  { code: 's1', label: 'Поддержка 1' },
  { code: 's2', label: 'Поддержка 2' },
  { code: 's3', label: 'Поддержка 3' },
  { code: 's4', label: 'Поддержка 4' },
  { code: 's5', label: 'Поддержка 5' },
  { code: 's6', label: 'Поддержка 6' },
  { code: 's7', label: 'Поддержка 7' },
  { code: 'other', label: 'Другое' },
];

export const SUPPORT_TEXT_MIN = 2;
export const SUPPORT_TEXT_MAX = 2000;

export type SupportTextCheck = 'nul' | 'short' | 'long' | 'ok';

/** Как на сервере: NUL → nul; меньше 2 кодовых точек после trim → short; больше 2000 по сырому → long. */
export function validateSupportText(s: string): SupportTextCheck {
  if (s.includes('\u0000')) return 'nul';
  if ([...s.trim()].length < SUPPORT_TEXT_MIN) return 'short';
  if ([...s].length > SUPPORT_TEXT_MAX) return 'long';
  return 'ok';
}

export const SUPPORT_TEXT_HINTS: Record<Exclude<SupportTextCheck, 'ok'>, string> = {
  short: 'Напишите вопрос: минимум 2 знака.',
  long: 'Слишком длинно: максимум 2000 знаков.',
  nul: 'В тексте есть недопустимый символ.',
};

/** Тот же id для повтора попытки; нового id нет — создать. */
export function opIdForSend(current: string | null, gen: () => string): string {
  return current ?? gen();
}

export const SUPPORT_ERROR_AUTH = 'Не удалось подтвердить вход. Закройте приложение и откройте снова.';
export const SUPPORT_RESTART_TEXT = 'Нужно заново проверить данные.';
export const SUPPORT_ERROR_TEXT = 'Проверьте вопрос: от 2 до 2000 знаков.';
export const SUPPORT_ERROR_LATER = 'Слишком часто. Попробуйте чуть позже.';
export const SUPPORT_ERROR_UNAVAILABLE = 'Сервис временно недоступен. Попробуйте позже.';
export const SUPPORT_ERROR_OTHER = 'Не удалось отправить. Попробуйте ещё раз.';
export const SUPPORT_SENT_TEXT = 'Вопрос отправлен.';

export type SupportErrorView = { kind: 'restart' } | { kind: 'message'; text: string };

export function supportErrorView(err: unknown): SupportErrorView {
  if (!(err instanceof ApiError)) return { kind: 'message', text: SUPPORT_ERROR_UNAVAILABLE };
  if (err.status === 401) return { kind: 'message', text: SUPPORT_ERROR_AUTH };
  if (
    (err.status === 404 && err.code === 'PARTICIPANT_NOT_FOUND') ||
    (err.status === 409 && err.code === 'RECONSENT_REQUIRED')
  ) {
    return { kind: 'restart' };
  }
  if (err.status === 422) return { kind: 'message', text: SUPPORT_ERROR_TEXT };
  if (err.status === 429) {
    const text = err.retryAfter !== null ? `Слишком часто. Попробуйте через ${err.retryAfter} с.` : SUPPORT_ERROR_LATER;
    return { kind: 'message', text };
  }
  if (err.status === 503) return { kind: 'message', text: SUPPORT_ERROR_UNAVAILABLE };
  return { kind: 'message', text: SUPPORT_ERROR_OTHER };
}

export function supportTopicLabel(code: SupportTopicCode | null): string {
  return SUPPORT_TOPICS.find((t) => t.code === code)?.label ?? '';
}

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };

export interface SupportTopicViewProps {
  selected: SupportTopicCode | null;
  onPick: (code: SupportTopicCode) => void;
  onBack: () => void;
}

export function SupportTopicView({ selected, onPick, onBack }: SupportTopicViewProps) {
  return (
    <div className="page" style={pageStyle}>
      <p>Выберите тему вопроса.</p>
      {SUPPORT_TOPICS.map((t) => (
        <button key={t.code} type="button" aria-pressed={t.code === selected} onClick={() => onPick(t.code)}>
          {t.label}
        </button>
      ))}
      <button type="button" onClick={onBack}>
        Назад
      </button>
    </div>
  );
}

export interface SupportQuestionViewProps {
  topic: SupportTopicCode | null;
  text: string;
  sending: boolean;
  error: SupportErrorView | null;
  onText: (text: string) => void;
  onSend: () => void;
  onBack: () => void;
  onRestart: () => void;
}

export function SupportQuestionView({
  topic,
  text,
  sending,
  error,
  onText,
  onSend,
  onBack,
  onRestart,
}: SupportQuestionViewProps) {
  const check = validateSupportText(text);
  return (
    <div className="page" style={pageStyle}>
      <p>Тема: {supportTopicLabel(topic)}</p>
      <textarea
        aria-label="Ваш вопрос"
        rows={6}
        value={text}
        disabled={sending}
        onChange={(e) => onText(e.target.value)}
      />
      {check !== 'ok' ? <p>{SUPPORT_TEXT_HINTS[check]}</p> : null}
      {error !== null && error.kind === 'message' ? <p role="alert">{error.text}</p> : null}
      {error !== null && error.kind === 'restart' ? (
        <>
          <p role="alert">{SUPPORT_RESTART_TEXT}</p>
          <button type="button" onClick={onRestart}>
            Повторить
          </button>
        </>
      ) : null}
      <button type="button" disabled={sending || check !== 'ok'} onClick={onSend}>
        Отправить
      </button>
      <button type="button" disabled={sending} onClick={onBack}>
        Назад
      </button>
    </div>
  );
}

export interface SupportScreenProps {
  tgUserId: number | null;
  store: SupportDraftStore;
  onBack: () => void;
  onRestart: () => void;
  /** По умолчанию postSupportQuestion; в тестах — подмена. */
  send?: (body: SupportQuestionBody, clientOpId: string) => Promise<unknown>;
}

type Step = 'loading' | 'topic' | 'question' | 'sent';

export function SupportScreen({ tgUserId, store, onBack, onRestart, send = postSupportQuestion }: SupportScreenProps) {
  const [step, setStep] = useState<Step>('loading');
  const [draft, setDraft] = useState<SupportDraft>(EMPTY_SUPPORT_DRAFT);
  const [opId, setOpId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<SupportErrorView | null>(null);
  const mountedRef = useRef(true);
  const sendingRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Черновик открывается один раз; openSupportDraft не бросает (ошибка → пустой черновик).
  useEffect(() => {
    let cancelled = false;
    void openSupportDraft(store, tgUserId, Date.now()).then((found) => {
      if (cancelled) return;
      setDraft(found);
      setStep(found.topic === null ? 'topic' : 'question');
    });
    return () => {
      cancelled = true;
    };
  }, [store, tgUserId]);

  // Каждое изменение темы или текста: новый op_id при следующей отправке и запись черновика.
  const change = (next: SupportDraft) => {
    setDraft(next);
    setOpId(null);
    setError(null);
    void saveSupportDraft(store, tgUserId, next, Date.now());
  };

  const submit = () => {
    const topic = draft.topic;
    if (sendingRef.current || topic === null || validateSupportText(draft.text) !== 'ok') return;
    const id = opIdForSend(opId, newClientOpId);
    const body: SupportQuestionBody = { topic_code: topic, text: draft.text };
    sendingRef.current = true;
    setOpId(id);
    setSending(true);
    setError(null);
    Promise.resolve()
      .then(() => send(body, id))
      .then(() => {
        sendingRef.current = false;
        void clearSupportDraft(store);
        if (!mountedRef.current) return;
        setDraft(EMPTY_SUPPORT_DRAFT);
        setOpId(null);
        setSending(false);
        setStep('sent');
      })
      .catch((err: unknown) => {
        sendingRef.current = false;
        if (!mountedRef.current) return;
        setSending(false);
        setError(supportErrorView(err));
      });
  };

  if (step === 'loading') {
    return (
      <div className="page" style={pageStyle}>
        <p>Загрузка…</p>
      </div>
    );
  }

  if (step === 'sent') {
    return (
      <div className="page" style={pageStyle}>
        <p>{SUPPORT_SENT_TEXT}</p>
        <button type="button" onClick={onBack}>
          Назад
        </button>
      </div>
    );
  }

  if (step === 'topic') {
    return (
      <SupportTopicView
        selected={draft.topic}
        onPick={(code) => {
          if (code !== draft.topic) change({ topic: code, text: draft.text });
          setStep('question');
        }}
        onBack={onBack}
      />
    );
  }

  return (
    <SupportQuestionView
      topic={draft.topic}
      text={draft.text}
      sending={sending}
      error={error}
      onText={(text) => change({ topic: draft.topic, text })}
      onSend={submit}
      onBack={() => {
        setError(null);
        setStep('topic');
      }}
      onRestart={onRestart}
    />
  );
}
