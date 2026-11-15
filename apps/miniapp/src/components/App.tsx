// apps/miniapp/src/components/App.tsx
// HashRouter (как в шаблоне): не требует серверного роутинга и не конфликтует
// с путём /miniapp/, занятым мониторингом на IRONCLAD (SERVER-IRONCLAD.md).
//
// Фазы (block_all_ui_until_checked; returning-2):
//   checking    — первая фаза: «Загрузка…» и один GET /miniapp/v1/onboarding/status;
//                 больше ничего не показывается и не монтируется;
//   start-error — status не получен (401 / 429 / 503 / сеть / прочее): текст и «Повторить»
//                 → снова checking. Ошибка status НИКОГДА не ведёт ни в онбординг, ни к номеру;
//   no-access   — status no_access или 403 ACCESS_NOT_GRANTED из first-launch (Р-2): текст
//                 «доступ не открыт» и «Проверить ещё раз» → снова checking (один GET status);
//                 OnboardingFlow не монтируется, номера нет, черновик не открывается;
//   number      — сервер ответил returning: «Ваш номер участника» и «Продолжить» →
//                 незаконченный черновик моложе 24 ч → later; иначе GET /onboarding/form:
//                 нет → later с оферты; отправлена → GET /checkup/status: пройден → app,
//                 нет → later с шага checkup; ошибка любого GET → start-error
//                 (miniapp-i3-1a/1b §7.4: день недоступен без пройденного онбординга, 04 §4.7);
//   onboarding  — new / reconsent / непонятный ответ: OnboardingFlow до pid (1e-1b);
//                 после него: new → later, reconsent → то же правило, что после номера;
//   later       — LaterSteps после pid (1e-2, miniapp-i3-1a): offer → form → checkup → rules;
//                 анкета (form) — на сервере; черновик — drafts.ts, только шаг, привязан к tg_user_id;
//                 экран restart анкеты → retry (снова checking);
//   app         — роутер: экран дня /day; путь «/» и любой другой → /day (З2, вариант А).
// miniapp-i3-2: маршруты фазы app — список в navigation/routes.tsx; логика фаз не менялась
// miniapp-sup-1 (Р-19): кнопка «Помощь» внизу — только в фазах later и app (после 18+ и согласий);
//   в checking, start-error, no-access, number и onboarding её нет. later: SupportScreen поверх
//   скрытого, но смонтированного LaterSteps (ответы экрана в памяти не теряются, Р-16, Р-18);
//   app: маршрут /help в этом файле (routes.tsx не трогаем) и HelpBar под Routes.
//   Черновик вопроса — drafts.ts (createSupportDraftStore), отдельно от черновика шага.
// OnboardingFlow монтируется ТОЛЬКО в фазе onboarding (он шлёт /texts/bulk при монтировании).
// «Пускать ли» решает сервер: клиент не смотрит ни initDataUnsafe, ни черновик, ни время.
// short_no, status и reasons на устройстве не хранятся — только в памяти до закрытия.
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import { getCheckupStatus, getForm, getOnboardingStatus, readTgUserId } from '@/api/client.ts';
import {
  createDraftStore,
  createSupportDraftStore,
  openDraft,
  type LaterStep,
  type SupportDraftStore,
} from '@/components/drafts.ts';
import { LaterSteps } from '@/components/LaterSteps.tsx';
import { OnboardingFlow } from '@/components/OnboardingFlow.tsx';
import {
  NO_ACCESS_BUTTON,
  NO_ACCESS_TEXT,
  afterNumber,
  isAccessNotGranted,
  isReconsent,
  returningShortNo,
  startErrorMessage,
  startPhase,
} from '@/components/startup.ts';
import { SupportScreen } from '@/components/SupportScreen.tsx';
import { routes } from '@/navigation/routes.tsx';

type Phase = 'checking' | 'start-error' | 'no-access' | 'number' | 'onboarding' | 'later' | 'app';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const helpBarStyle: CSSProperties = { position: 'sticky', bottom: 0, padding: 16 };

/** Нижняя панель с кнопкой «Помощь». */
function HelpButtonBar({ onHelp }: { onHelp: () => void }) {
  return (
    <div style={helpBarStyle}>
      <button type="button" onClick={onHelp}>
        Помощь
      </button>
    </div>
  );
}

/** Фаза app: панель «Помощь» под маршрутами; на /help не показывается. */
function HelpBar() {
  const location = useLocation();
  const navigate = useNavigate();
  if (location.pathname === '/help') return null;
  return <HelpButtonBar onHelp={() => navigate('/help')}/>;
}

interface HelpRouteProps {
  tgUserId: number | null;
  store: SupportDraftStore;
  onRestart: () => void;
}

/** Фаза app, маршрут /help: «Назад» — на прошлый экран; открыли сразу /help — на /day. */
function HelpRoute({ tgUserId, store, onRestart }: HelpRouteProps) {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <SupportScreen
      tgUserId={tgUserId}
      store={store}
      onRestart={onRestart}
      onBack={() => {
        if (location.key === 'default') navigate('/day', { replace: true });
        else navigate(-1);
      }}
    />
  );
}

export function App() {
  const [phase, setPhase] = useState<Phase>('checking');
  const [attempt, setAttempt] = useState(0);
  const [shortNo, setShortNo] = useState('');
  const [startError, setStartError] = useState<unknown>(null);
  const [reconsent, setReconsent] = useState(false);
  const [routing, setRouting] = useState(false);
  const [initialStep, setInitialStep] = useState<LaterStep>('offer');
  const [helpOpen, setHelpOpen] = useState(false);
  const routingRef = useRef(false);
  const [tgUserId] = useState(() => readTgUserId());
  const [draftStore] = useState(() => createDraftStore());
  const [supportStore] = useState(() => createSupportDraftStore());

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
        if (startPhase(resp) === 'no-access') {
          setPhase('no-access');
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
    routingRef.current = false;
    setRouting(false);
    setStartError(null);
    setHelpOpen(false);
    setPhase('checking');
    setAttempt((n) => n + 1);
  };

  // После номера (и после reconsent): незаконченный черновик → шаги онбординга. Черновика нет,
  // finished или ошибка хранилища → GET /onboarding/form: нет → с оферты; отправлена →
  // GET /checkup/status: пройден → курс, нет → с шага checkup.
  // Ошибка любого GET → start-error; «Повторить» → checking.
  const routeByDraft = () => {
    if (routingRef.current) return;
    routingRef.current = true;
    setRouting(true);
    Promise.resolve()
      .then(() => openDraft(draftStore, tgUserId, Date.now()))
      .catch(() => null)
      .then(async (draft) => {
        if (draft !== null && draft.step !== 'finished') {
          // Незаконченный черновик важнее initialStep (он восстановится в LaterSteps).
          setInitialStep('offer');
          setPhase('later');
          return;
        }
        const form = await getForm();
        // GET checkup/status — только когда анкета отправлена.
        const checkupCompleted = form.submitted ? (await getCheckupStatus()).completed : false;
        const next = afterNumber(draft, form.submitted, checkupCompleted);
        setInitialStep(next === 'checkup' ? 'checkup' : 'offer');
        setPhase(next === 'checkup' ? 'later' : next);
      })
      .catch((err: unknown) => {
        routingRef.current = false;
        setRouting(false);
        setStartError(err);
        setPhase('start-error');
      });
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

  if (phase === 'no-access') {
    return (
      <div className="page" style={pageStyle}>
        <p>{NO_ACCESS_TEXT}</p>
        <button type="button" onClick={retry}>
          {NO_ACCESS_BUTTON}
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
        onSubmitError={(err) => {
          if (!isAccessNotGranted(err)) return false;
          setPhase('no-access');
          return true;
        }}
      />
    );
  }

  if (phase === 'later') {
    // LaterSteps всегда в одном месте дерева: при «Помощи» он скрыт, но не размонтирован.
    return (
      <>
        <div hidden={helpOpen}>
          <LaterSteps
            tgUserId={tgUserId}
            store={draftStore}
            initialStep={initialStep}
            onFinish={() => {
              setHelpOpen(false);
              setPhase('app');
            }}
            onRestart={retry}
          />
        </div>
        {helpOpen ? (
          <SupportScreen
            tgUserId={tgUserId}
            store={supportStore}
            onBack={() => setHelpOpen(false)}
            onRestart={retry}
          />
        ) : (
          <HelpButtonBar onHelp={() => setHelpOpen(true)}/>
        )}
      </>
    );
  }

  return (
    <HashRouter>
      <Routes>
        {routes.map((route) => <Route key={route.path} {...route}/>)}
        <Route path="/help" element={<HelpRoute tgUserId={tgUserId} store={supportStore} onRestart={retry}/>}/>
        <Route path="*" element={<Navigate to="/day"/>}/>
      </Routes>
      <HelpBar/>
    </HashRouter>
  );
}
