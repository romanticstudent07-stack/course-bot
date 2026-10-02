// apps/miniapp/src/components/App.tsx
// HashRouter (как в шаблоне): не требует серверного роутинга и не конфликтует
// с путём /miniapp/, занятым мониторингом на IRONCLAD (SERVER-IRONCLAD.md).
//
// 1e-1b (D-14, block_all_ui_until_checked): пока онбординг не дошёл до шага done
// и пользователь не нажал «Начать», рендерится ТОЛЬКО OnboardingFlow — роутер и
// остальной UI недоступны. «Онбординг пройден» между запусками не запоминаем (это 1e-2):
// повторный first-launch возвращает тот же pid и не создаёт дублей согласий.
import { useState } from 'react';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';

import { OnboardingFlow } from '@/components/OnboardingFlow.tsx';
import { routes } from '@/navigation/routes.tsx';

export function App() {
  const [onboarded, setOnboarded] = useState(false);

  if (!onboarded) {
    return <OnboardingFlow onComplete={() => setOnboarded(true)}/>;
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
