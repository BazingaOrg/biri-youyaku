import {Route, Switch} from 'wouter'
import {AppShell} from './components/AppShell'
import {Workspace} from './pages/Workspace'
import {ToastProvider} from './components/ToastProvider'
import {ThemeProvider} from './components/ThemeProvider'

export default function App() {
  return (
    <ThemeProvider>
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
    </ThemeProvider>
  )
}
