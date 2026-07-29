import type {ReactNode} from 'react'
import {ScrollToTop} from './ScrollToTop'
import {ThemeToggle} from './ThemeToggle'

interface AppShellProps {
  children: ReactNode
}

// 极简外壳：无顶栏、品牌名、导航；右下角为全局工具区（主题 + 回到顶部）。
export function AppShell({children}: AppShellProps) {
  return (
    <div className="min-h-screen text-ink">
      {/* body 已带和纸纹背景；这里不能再覆一层 bg-canvas，否则把纹遮住 */}
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
