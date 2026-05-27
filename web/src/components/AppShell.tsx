import type {ReactNode} from 'react'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({children}: AppShellProps) {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <main className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-6 sm:py-8">{children}</main>
    </div>
  )
}
