import { Navigate, type RouteObject } from 'react-router-dom';
import { PageContainer } from '@/components/PageContainer';
import { AskPage } from '@/features/ask/AskPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { RequireSession } from '@/features/auth/RequireSession';
import { CheckPage } from '@/features/check/CheckPage';
import { ComparePage } from '@/features/compare/ComparePage';
import { ConflictsPage } from '@/features/conflicts/ConflictsPage';
import { LibraryPage } from '@/features/library/LibraryPage';
import { WelcomePage } from '@/features/welcome/WelcomePage';
import { env } from '@/lib/env';
import { AppLayout } from './AppLayout';
import { NotFoundPage } from './NotFoundPage';

// The component kit is dev-only; in production builds this branch and its chunk are dropped.
const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: '_kit',
        lazy: async () => {
          const { KitPage } = await import('./kit/KitPage');
          return { Component: KitPage };
        },
        // Shown while the lazy route loads on a direct visit to /_kit.
        hydrateFallbackElement: (
          <PageContainer>
            <p className="font-mono text-label uppercase text-muted">Loading kit…</p>
          </PageContainer>
        ),
      },
    ]
  : [];

export const routes: RouteObject[] = [
  { path: '/welcome', element: <WelcomePage /> },
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireSession />,
    children: [
      {
        path: '/',
        element: <AppLayout />,
        children: [
          {
            index: true,
            // VITE_ENABLE_CLAIM_MODE=false hides the Check screen.
            element: env.enableClaimMode ? <CheckPage /> : <Navigate to="/library" replace />,
          },
          { path: 'library', element: <LibraryPage /> },
          { path: 'ask', element: <AskPage /> },
          { path: 'compare', element: <ComparePage /> },
          { path: 'conflicts', element: <ConflictsPage /> },
          ...devRoutes,
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

// Opt in to React Router v7 behaviour now, which also silences v6's upgrade warnings.
export const routerFuture = {
  v7_fetcherPersist: true,
  v7_normalizeFormMethod: true,
  v7_partialHydration: true,
  v7_relativeSplatPath: true,
  v7_skipActionErrorRevalidation: true,
} as const;

export const providerFuture = { v7_startTransition: true } as const;
