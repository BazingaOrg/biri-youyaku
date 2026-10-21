import type {ReactNode} from 'react'
import {Link, useLocation} from 'wouter'
import {BookOpen, ListTodo} from 'lucide-react'
import {BrandMark} from './BrandMark'
import {ScrollToTop} from './ScrollToTop'
import {ThemeToggle} from './ThemeToggle'
import {useTaskAlerts} from '../hooks/useTaskAlerts'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({children}: AppShellProps) {
  const [location] = useLocation()
  const {badge} = useTaskAlerts()
  const notesOn =
    location === '/' ||
    location.startsWith('/search') ||
    location.startsWith('/doc') ||
    location === '/trash'
  const tasksOn = location.startsWith('/tasks') || location.startsWith('/jobs')

  return (
    <div className="min-h-screen text-ink">
      <header className="sticky top-0 z-20 border-b border-transparent bg-canvas/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4 sm:h-14 sm:px-6">
          <Link
            href="/"
            aria-label="笔哩 首页"
            className="inline-flex min-w-0 items-center gap-2.5 font-serif text-[19px] font-bold tracking-[0.04em]"
          >
            <BrandMark />
            <span className="truncate">笔哩</span>
          </Link>
          <span className="flex-1" />
          <Link
            href="/"
            className={`inline-flex h-9 items-center gap-1.5 rounded-[10px] px-3 text-sm ${
              notesOn ? 'font-medium text-ink' : 'text-muted hover:bg-lift hover:text-ink'
            }`}
          >
            <BookOpen size={18} />
            <span className="hidden sm:inline">笔记</span>
          </Link>
          <Link
            href="/tasks"
            className={`relative inline-flex h-9 items-center gap-1.5 rounded-[10px] px-3 text-sm ${
              tasksOn ? 'font-medium text-ink' : 'text-muted hover:bg-lift hover:text-ink'
            }`}
          >
            <ListTodo size={18} />
            <span className="hidden sm:inline">任务</span>
            {badge > 0 ? (
              <span className="min-w-[18px] rounded-full bg-brandSolid px-1.5 text-center text-[11px] leading-[18px] text-onBrand tabular-nums">
                {badge > 99 ? '99+' : badge}
              </span>
            ) : null}
          </Link>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto min-w-0 w-full max-w-5xl px-4 pb-16 pt-2 sm:px-6 sm:pt-4">{children}</main>
      <div className="fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-5 z-40 sm:right-6">
        <ScrollToTop />
      </div>
    </div>
  )
}
