// apps/miniapp/src/pages/HomePage/HomePage.tsx — экран курса (заглушка).
// Имя берётся из initData ТОЛЬКО для отрисовки (AGENTS.md, запрет №7).
import { initData, useSignal } from '@telegram-apps/sdk-react';

export function HomePage() {
  const user = useSignal(initData.user);

  return (
    <div className="page">
      <h1>{user?.first_name ? `Привет, ${user.first_name}!` : 'Привет!'}</h1>
      <p className="hint">Здесь будет курс (экран-заглушка).</p>
    </div>
  );
}
