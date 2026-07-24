import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { OverviewPage } from '../pages/overview/OverviewPage';
import { SystemPage } from '../pages/system/SystemPage';
import { EvidencePage } from '../pages/evidence/EvidencePage';
import { PersonalStatePage } from '../pages/state/PersonalStatePage';
import { ExternalContextPage } from '../pages/external/ExternalContextPage';
import { DecisionCenterPage } from '../pages/decisions/DecisionCenterPage';
import { DecisionWorkspacePage } from '../pages/decisions/DecisionWorkspacePage';
import { SessionPage } from '../pages/sessions/SessionPage';
import { ActionsPage } from '../pages/actions/ActionsPage';
import { ProactivePage } from '../pages/proactive/ProactivePage';

// 8 条路由对应 spec §6.1 八项主导航；state/external/decisions/actions/proactive 已接真实页面
// （Phase 37/38/39），decisions 含列表 + 工作区 + 会话推进（写流程）；无占位页剩余。
// 导出路由表供冒烟测试用 createMemoryRouter 复用（与生产路由一致，不另维护副本）。
export const appRoutes = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'state', element: <PersonalStatePage /> },
      { path: 'state/:domain', element: <PersonalStatePage /> },
      { path: 'decisions', element: <DecisionCenterPage /> },
      { path: 'decisions/:id', element: <DecisionWorkspacePage /> },
      { path: 'sessions/:id', element: <SessionPage /> },
      { path: 'actions', element: <ActionsPage /> },
      { path: 'external', element: <ExternalContextPage /> },
      { path: 'proactive', element: <ProactivePage /> },
      { path: 'evidence', element: <EvidencePage /> },
      { path: 'system', element: <SystemPage /> },
    ],
  },
];

const router = createBrowserRouter(
  appRoutes,
  // 生产由 rag-api 托管在 /app/（vite base 同为 /app/）
  { basename: import.meta.env.BASE_URL },
);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
