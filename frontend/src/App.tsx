import { createHashRouter, RouterProvider } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { OverviewPage } from './pages/Overview';
import { OrchestrationPage } from './pages/Orchestration';
import { EdgeNodePage } from './pages/EdgeNode';
import { CloudNodePage } from './pages/CloudNode';
import { WorkloadsPage } from './pages/Workloads';
import { InferenceMonitorPage } from './pages/InferenceMonitor';
import { LogsPage } from './pages/Logs';
import { NotFoundPage } from './pages/NotFound';

const router = createHashRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'orchestration', element: <OrchestrationPage /> },
      { path: 'inference', element: <InferenceMonitorPage /> },
      { path: 'edge', element: <EdgeNodePage /> },
      { path: 'cloud', element: <CloudNodePage /> },
      { path: 'workloads', element: <WorkloadsPage /> },
      { path: 'logs', element: <LogsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
