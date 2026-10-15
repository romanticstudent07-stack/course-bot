// apps/miniapp/src/components/Root.tsx
// Корень приложения. Из шаблона убран TonConnectUIProvider: TON-кошелёк проекту не нужен,
// а оплата внутри Mini App пока запрещена (AGENTS.md, запрет №10).
// При сбое — нейтральный экран без error.message (miniapp-fix-1, D-23).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { App } from '@/components/App.tsx';
import { ErrorBoundary, NeutralErrorFallback } from '@/components/ErrorBoundary.tsx';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export function Root() {
  return (
    <ErrorBoundary fallback={NeutralErrorFallback}>
      <QueryClientProvider client={queryClient}>
        <App/>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
