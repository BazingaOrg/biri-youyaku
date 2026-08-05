import {lazy, Suspense} from 'react'
import {Route, Switch} from 'wouter'
import {AppShell} from './components/AppShell'
import {ErrorBoundary} from './components/ErrorBoundary'
import {Workspace} from './pages/Workspace'
import {ToastProvider} from './components/ToastProvider'
import {PageLoading} from './components/Spinner'

const HistoryPage = lazy(() => import('./pages/HistoryPage').then((m) => ({default: m.HistoryPage})))
const UpPage = lazy(() => import('./pages/UpPage').then((m) => ({default: m.UpPage})))
const KnowledgePage = lazy(() =>
  import('./pages/KnowledgePage').then((m) => ({default: m.KnowledgePage})),
)

export default function App() {
  // 主题三档（系统/白天/黑夜）由 AppShell 右下工具区的 ThemeToggle 管理。
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AppShell>
          <Switch>
          <Route path="/history">
            <Suspense fallback={<PageLoading />}>
              <HistoryPage />
            </Suspense>
          </Route>
          <Route path="/knowledge">
            <Suspense fallback={<PageLoading />}>
              <KnowledgePage />
            </Suspense>
          </Route>
          <Route path="/up/:mid">
            {(params) => (
              <Suspense fallback={<PageLoading />}>
                <UpPage mid={params.mid} />
              </Suspense>
            )}
          </Route>
          <Route path="/jobs/:jobId">
            {(params) => <Workspace jobId={params.jobId} />}
          </Route>
          <Route>
            <Workspace jobId={null} />
          </Route>
          </Switch>
        </AppShell>
      </ToastProvider>
    </ErrorBoundary>
  )
}
