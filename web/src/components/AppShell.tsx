import type {ReactNode} from 'react'
import {History, Home, Moon, Sun, Monitor} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {useTheme} from './ThemeProvider'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({children}: AppShellProps) {
  const [location] = useLocation()
  const {theme, cycleTheme} = useTheme()
  const title = location.startsWith('/jobs/') ? '任务' : location === '/history' ? '历史' : '首页'
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-line/80 bg-panel/90 backdrop-blur">
        <div className="mx-auto flex min-h-16 w-full max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <Link href="/" className="flex min-w-0 items-center gap-3 rounded-xl pr-2 transition active:scale-95">
            <img src="/logo-mark.svg" alt="biri-youyaku" className="h-8 w-8 shrink-0 sm:hidden" />
            <img src="/logo-full.svg" alt="biri-youyaku" className="hidden h-7 w-auto sm:block" />
          </Link>
          <div className="min-w-0 flex-1 text-center text-sm font-medium text-muted">
            {title}
          </div>
          <div className="flex items-center gap-2">
            <Link href="/" aria-label="首页" className="grid h-11 w-11 place-items-center rounded-xl text-muted transition hover:bg-lift hover:text-ink active:scale-95">
              <Home size={18} />
            </Link>
            <Link href="/history" aria-label="历史" className="grid h-11 w-11 place-items-center rounded-xl text-muted transition hover:bg-lift hover:text-ink active:scale-95">
              <History size={18} />
            </Link>
            <button type="button" aria-label={`主题：${theme}`} onClick={cycleTheme} className="grid h-11 w-11 place-items-center rounded-xl text-muted transition hover:bg-lift hover:text-ink active:scale-95">
              <ThemeIcon size={18} />
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-4 py-5 sm:px-6 sm:py-8">{children}</main>
    </div>
  )
}
