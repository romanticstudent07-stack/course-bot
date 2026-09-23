// apps/miniapp/src/pages/HomePage/HomePage.tsx — стартовый экран скелета (Итерация 0-А).
// Имя берётся из initData ТОЛЬКО для отрисовки (AGENTS.md, запрет №7).
// Экраны онбординга SEAM-1 (возрастной гейт → pid) — Итерация 1.
import { initData, useSignal } from '@telegram-apps/sdk-react';

export function HomePage() {
  const user = useSignal(initData.user);

  return (
    <div className="page">
      <h1>{user?.first_name ? `Привет, ${user.first_name}!` : 'Привет!'}</h1>
      <p className="hint">Mini App — скелет Итерации 0-А. Онбординг появится в Итерации 1.</p>
    </div>
  );
}
