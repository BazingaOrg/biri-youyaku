import {createContext, useContext, useEffect, useMemo, useState} from 'react'
import type {ReactNode} from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'

interface ThemeContextValue {
  theme: ThemeMode
  cycleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)
const storageKey = 'biri-youyaku-theme'
const modes: ThemeMode[] = ['system', 'light', 'dark']

function readInitialTheme(): ThemeMode {
  const stored = window.localStorage.getItem(storageKey)
  return modes.includes(stored as ThemeMode) ? stored as ThemeMode : 'system'
}

export function ThemeProvider({children}: {children: ReactNode}) {
  const [theme, setTheme] = useState<ThemeMode>(readInitialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem(storageKey, theme)
  }, [theme])

  const value = useMemo<ThemeContextValue>(() => ({
    theme,
    cycleTheme: () => setTheme((current) => modes[(modes.indexOf(current) + 1) % modes.length]),
  }), [theme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used inside ThemeProvider')
  }
  return context
}
