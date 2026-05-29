import {useState} from 'react'
import {Route, Switch, useLocation} from 'wouter'
import {AppShell} from './components/AppShell'
import {HistoryPage} from './pages/HistoryPage'
import {HomePage} from './pages/HomePage'
import {JobPage} from './pages/JobPage'
import {ToastProvider} from './components/ToastProvider'
import {ThemeProvider} from './components/ThemeProvider'
import {useShortcuts} from './hooks/useShortcuts'

export default function App() {
  const [, navigate] = useLocation()
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  useShortcuts({onHelp: () => setShortcutsOpen(true)})

  return (
    <ThemeProvider>
      <ToastProvider>
        <AppShell>
          <Switch>
            <Route path="/history">
              <HistoryPage onOpen={(id) => navigate(`/jobs/${id}`)} />
            </Route>
            <Route path="/jobs/:jobId">
              {(params) => <JobPage jobId={params.jobId} />}
            </Route>
            <Route>
              <HomePage onCreated={(id) => navigate(`/jobs/${id}`)} />
            </Route>
          </Switch>
        </AppShell>
        {shortcutsOpen && (
          <div className="fixed inset-0 z-40 grid place-items-center bg-ink/30 p-4 backdrop-blur-sm">
            <div className="w-full max-w-[420px] rounded-3xl bg-panel p-6 shadow-card">
              <h2 className="text-lg font-semibold">快捷键</h2>
              <div className="mt-4 grid gap-2 text-sm text-muted">
                <p><kbd>Cmd/Ctrl + V</kbd> 粘贴链接</p>
                <p><kbd>Cmd/Ctrl + Enter</kbd> 预检 / 开始 / 确认</p>
                <p><kbd>Cmd/Ctrl + .</kbd> 取消当前任务</p>
                <p><kbd>Cmd/Ctrl + K</kbd> 聚焦搜索</p>
                <p><kbd>?</kbd> 打开快捷键</p>
              </div>
              <button type="button" onClick={() => setShortcutsOpen(false)} className="mt-5 min-h-11 w-full rounded-2xl bg-brand px-4 text-sm font-semibold text-white transition active:scale-95">关闭</button>
            </div>
          </div>
        )}
      </ToastProvider>
    </ThemeProvider>
  )
}
