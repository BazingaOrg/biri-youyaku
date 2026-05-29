import type {ReactNode} from 'react'

interface AppShellProps {
  children: ReactNode
}

// 极简外壳：去掉顶栏、品牌名、导航、主题切换。
// 仅保留居中容器；明暗跟随系统（见 styles.css 的 prefers-color-scheme）。
export function AppShell({children}: AppShellProps) {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <main className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-10">{children}</main>
    </div>
  )
}
