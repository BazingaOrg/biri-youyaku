import type {ReactNode} from 'react'
import {ScrollToTop} from './ScrollToTop'
import {ThemeToggle} from './ThemeToggle'

interface AppShellProps {
  children: ReactNode
}

// 极简外壳：无顶栏、品牌名、导航；仅居中容器 + 右上角主题切换。
export function AppShell({children}: AppShellProps) {
  return (
    <div className="min-h-screen text-ink">
      {/* body 已带和纸纹背景；这里不能再覆一层 bg-canvas，否则把纹遮住 */}
      <main className="mx-auto min-w-0 w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-10">{children}</main>
      <ThemeToggle />
      <ScrollToTop />
    </div>
  )
}
