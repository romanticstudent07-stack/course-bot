// apps/miniapp/src/components/App.tsx
// HashRouter (как в шаблоне): не требует серверного роутинга и не конфликтует
// с путём /miniapp/, занятым мониторингом на IRONCLAD (SERVER-IRONCLAD.md).
//
// Фазы (block_all_ui_until_checked):
//   onboarding — OnboardingFlow до pid (1e-1b): пока не нажата «Начать», ничего другого нет;
//   later      — LaterSteps после pid (1e-2): offer → email → city → checkup → rules;
//                черновик — drafts.ts, привязан к tg_user_id;
//   app        — роутер и остальной UI.
// «Онбординг пройден» между запусками не запоминается: повторный first-launch возвращает
// тот же pid и не создаёт дублей согласий; после него LaterSteps открывает черновик
// на сохранённом шаге.
import { useState } from 'react';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';

import { readTgUserId } from '@/api/client.ts';
import { createDraftStore } from '@/components/drafts.ts';
import { LaterSteps } from '@/components/LaterSteps.tsx';
import { OnboardingFlow } from '@/components/OnboardingFlow.tsx';
import { routes } from '@/navigation/routes.tsx';

type Phase = 'onboarding' | 'later' | 'app';

export function App() {
  const [phase, setPhase] = useState<Phase>('onboarding');
  const [tgUserId] = useState(() => readTgUserId());
  const [draftStore] = useState(() => createDraftStore());

  if (phase === 'onboarding') {
    return <OnboardingFlow onComplete={() => setPhase('later')}/>;
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
