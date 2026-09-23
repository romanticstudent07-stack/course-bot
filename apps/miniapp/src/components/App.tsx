// apps/miniapp/src/components/App.tsx
// HashRouter (как в шаблоне): не требует серверного роутинга и не конфликтует
// с путём /miniapp/, занятым мониторингом на IRONCLAD (SERVER-IRONCLAD.md).
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';

import { routes } from '@/navigation/routes.tsx';

export function App() {
  return (
    <HashRouter>
      <Routes>
        {routes.map((route) => <Route key={route.path} {...route}/>)}
        <Route path="*" element={<Navigate to="/"/>}/>
      </Routes>
    </HashRouter>
  );
}
