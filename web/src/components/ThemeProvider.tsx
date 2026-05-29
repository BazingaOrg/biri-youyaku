import type {ReactNode} from 'react'

// 主题完全跟随系统（prefers-color-scheme），不再提供切换 UI。
// 保留 Provider 仅为兼容现有 import；后续如确无引用可一并删除。
export function ThemeProvider({children}: {children: ReactNode}) {
  return <>{children}</>
}
