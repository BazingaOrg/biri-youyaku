import {Route, Switch} from 'wouter'
import {AppShell} from './components/AppShell'
import {Workspace} from './pages/Workspace'
import {ToastProvider} from './components/ToastProvider'

export default function App() {
  // 主题完全跟随系统（prefers-color-scheme，见 styles.css）。
  // 如果未来需要人工切换主题，再恢复 ThemeProvider 包一层。
  return (
    <ToastProvider>
      <AppShell>
        <Switch>
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
