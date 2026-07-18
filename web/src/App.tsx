import {lazy, Suspense} from 'react'
import {Route, Switch} from 'wouter'
import {AppShell} from './components/AppShell'
import {Workspace} from './pages/Workspace'
import {ToastProvider} from './components/ToastProvider'
import {PageLoading} from './components/Spinner'

const HistoryPage = lazy(() => import('./pages/HistoryPage').then((m) => ({default: m.HistoryPage})))
const StatsPage = lazy(() => import('./pages/StatsPage').then((m) => ({default: m.StatsPage})))
const UpPage = lazy(() => import('./pages/UpPage').then((m) => ({default: m.UpPage})))

export default function App() {
  // 主题完全跟随系统（prefers-color-scheme，见 styles.css）。
  // 如果未来需要人工切换主题，再恢复 ThemeProvider 包一层。
  return (
    <ToastProvider>
      <AppShell>
        <Switch>
          <Route path="/history">
            <Suspense fallback={<PageLoading />}>
              <HistoryPage />
            </Suspense>
          </Route>
          <Route path="/stats">
            <Suspense fallback={<PageLoading />}>
              <StatsPage />
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
  )
}
