import type {ReactNode} from 'react'
import {useLocation} from 'wouter'
import {ScrollToTop} from './ScrollToTop'
import {ThemeToggle} from './ThemeToggle'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({children}: AppShellProps) {
  const [location] = useLocation()
  const contentSurface = location === '/' ? '' : 'bg-canvas/95'

  return (
    <div className={`min-h-screen text-ink ${contentSurface}`}>
      <main className="mx-auto min-w-0 w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-10">{children}</main>
      {/* flex-col-reverse：主题始终贴底，回顶出现时叠在主题上方 */}
      <div className="pointer-events-none fixed bottom-5 right-5 z-40 flex flex-col-reverse items-end gap-2 sm:bottom-6 sm:right-6">
        <div className="pointer-events-auto">
          <ThemeToggle />
        </div>
        <div className="pointer-events-auto">
          <ScrollToTop />
        </div>
      </div>
    </div>
  )
}
