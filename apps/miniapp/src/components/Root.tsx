// apps/miniapp/src/components/Root.tsx
// Корень приложения. Из шаблона убран TonConnectUIProvider: TON-кошелёк проекту не нужен,
// а оплата внутри Mini App пока запрещена (AGENTS.md, запрет №10).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { App } from '@/components/App.tsx';
import { ErrorBoundary } from '@/components/ErrorBoundary.tsx';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

function ErrorBoundaryError({ error }: { error: unknown }) {
  return (
    <div className="page">
      <p>Произошла непредвиденная ошибка:</p>
      <blockquote>
        <code>
          {error instanceof Error
            ? error.message
            : typeof error === 'string'
              ? error
              : JSON.stringify(error)}
        </code>
      </blockquote>
    </div>
  );
}

export function Root() {
  return (
    <ErrorBoundary fallback={ErrorBoundaryError}>
      <QueryClientProvider client={queryClient}>
        <App/>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
