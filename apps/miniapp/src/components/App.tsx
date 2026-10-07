// apps/miniapp/src/components/App.tsx
// HashRouter (как в шаблоне): не требует серверного роутинга и не конфликтует
// с путём /miniapp/, занятым мониторингом на IRONCLAD (SERVER-IRONCLAD.md).
//
// Фазы (block_all_ui_until_checked; returning-2):
//   checking    — первая фаза: «Загрузка…» и один GET /miniapp/v1/onboarding/status;
//                 больше ничего не показывается и не монтируется;
//   start-error — status не получен (401 / 429 / 503 / сеть / прочее): текст и «Повторить»
//                 → снова checking. Ошибка status НИКОГДА не ведёт ни в онбординг, ни к номеру;
//   number      — сервер ответил returning: «Ваш номер участника» и «Продолжить» →
//                 незаконченный черновик моложе 24 ч → later, иначе → app;
//   onboarding  — new / reconsent / непонятный ответ: OnboardingFlow до pid (1e-1b);
//                 после него: new → later, reconsent → то же правило, что после номера;
//   later       — LaterSteps после pid (1e-2): offer → email → city → checkup → rules;
//                 черновик — drafts.ts, привязан к tg_user_id;
//   app         — роутер и остальной UI.
// OnboardingFlow монтируется ТОЛЬКО в фазе onboarding (он шлёт /texts/bulk при монтировании).
// «Пускать ли» решает сервер: клиент не смотрит ни initDataUnsafe, ни черновик, ни время.
// short_no, status и reasons на устройстве не хранятся — только в памяти до закрытия.
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';

import { getOnboardingStatus, readTgUserId } from '@/api/client.ts';
import { createDraftStore, openDraft } from '@/components/drafts.ts';
import { LaterSteps } from '@/components/LaterSteps.tsx';
import { OnboardingFlow } from '@/components/OnboardingFlow.tsx';
import { afterNumber, isReconsent, returningShortNo, startErrorMessage, startPhase } from '@/components/startup.ts';
import { routes } from '@/navigation/routes.tsx';

type Phase = 'checking' | 'start-error' | 'number' | 'onboarding' | 'later' | 'app';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };

export function App() {
  const [phase, setPhase] = useState<Phase>('checking');
  const [attempt, setAttempt] = useState(0);
  const [shortNo, setShortNo] = useState('');
  const [startError, setStartError] = useState<unknown>(null);
  const [reconsent, setReconsent] = useState(false);
  const [routing, setRouting] = useState(false);
  const routingRef = useRef(false);
  const [tgUserId] = useState(() => readTgUserId());
  const [draftStore] = useState(() => createDraftStore());

  // Один запрос status на попытку (при монтировании и после «Повторить»).
  useEffect(() => {
    let cancelled = false;
    getOnboardingStatus()
      .then((resp: unknown) => {
        if (cancelled) return;
        const no = returningShortNo(resp);
        if (startPhase(resp) === 'number' && no !== null) {
          setShortNo(no);
          setPhase('number');
          return;
        }
        setReconsent(isReconsent(resp));
        setPhase('onboarding');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStartError(err);
        setPhase('start-error');
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = () => {
    setStartError(null);
    setPhase('checking');
    setAttempt((n) => n + 1);
  };

  // После номера (и после reconsent): черновик → анкета или курс. Ошибка хранилища → курс.
  const routeByDraft = () => {
    if (routingRef.current) return;
    routingRef.current = true;
    setRouting(true);
    Promise.resolve()
      .then(() => openDraft(draftStore, tgUserId, Date.now()))
      .catch(() => null)
      .then((draft) => setPhase(afterNumber(draft)));
  };

  if (phase === 'checking') {
    return (
      <div className="page" style={pageStyle}>
        <p>Загрузка…</p>
      </div>
    );
  }

  if (phase === 'start-error') {
    return (
      <div className="page" style={pageStyle}>
        <p>{startErrorMessage(startError)}</p>
        <button type="button" onClick={retry}>
          Повторить
        </button>
      </div>
    );
  }

  if (phase === 'number') {
    return (
      <div className="page" style={pageStyle}>
        <p>Ваш номер участника: {shortNo}</p>
        <button type="button" disabled={routing} onClick={routeByDraft}>
          Продолжить
        </button>
      </div>
    );
  }

  if (phase === 'onboarding') {
    return (
      <OnboardingFlow
        onComplete={() => {
          if (reconsent) routeByDraft();
          else setPhase('later');
        }}
      />
    );
  }

  if (phase === 'later') {
    return <LaterSteps tgUserId={tgUserId} store={draftStore} onFinish={() => setPhase('app')}/>;
  }

  return (
    <HashRouter>
      <Routes>
        {routes.map((route) => <Route key={route.path} {...route}/>)}
        <Route path="*" element={<Navigate to="/"/>}/>
      </Routes>
    </HashRouter>
  );
}
