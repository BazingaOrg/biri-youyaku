import {useEffect, useState} from 'react'
import {Monitor, Moon, Sun} from 'lucide-react'

type ThemeMode = 'system' | 'light' | 'dark'

declare global {
  interface Document {
    startViewTransition?: (update: () => void) => {ready: Promise<void>}
  }
}

const STORAGE_KEY = 'theme'
const MODES: ThemeMode[] = ['system', 'light', 'dark']
const LABEL: Record<ThemeMode, string> = {system: '跟随系统', light: '白天', dark: '黑夜'}
const SHORT: Record<ThemeMode, string> = {system: '系统', light: '白天', dark: '黑夜'}
const THEME_COLOR = {light: '#B33F66', dark: '#15131A'} as const

function readMode(): ThemeMode {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw === 'light' || raw === 'dark' ? raw : 'system'
  } catch {
    return 'system'
  }
}

function resolve(mode: ThemeMode): 'light' | 'dark' {
  return mode === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : mode
}

function applyResolved(resolved: 'light' | 'dark') {
  document.documentElement.dataset.theme = resolved
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
    .forEach((meta) => (meta.content = THEME_COLOR[resolved]))
}

export function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>(readMode)

  useEffect(() => {
    applyResolved(resolve(mode))
    if (mode !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyResolved(resolve('system'))
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [mode])

  const nextMode = MODES[(MODES.indexOf(mode) + 1) % MODES.length]
  const Icon = mode === 'system' ? Monitor : mode === 'light' ? Sun : Moon

  const cycleMode = () => {
    try {
      if (nextMode === 'system') window.localStorage.removeItem(STORAGE_KEY)
      else window.localStorage.setItem(STORAGE_KEY, nextMode)
    } catch {}

    const commit = () => setMode(nextMode)
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (resolve(nextMode) === resolve(mode) || reduceMotion || !document.startViewTransition) {
      commit()
      return
    }
    const toDark = resolve(nextMode) === 'dark'
    const transition = document.startViewTransition(() => {
      applyResolved(resolve(nextMode))
      commit()
    })
    void transition.ready.then(() => {
      document.documentElement.animate(
        {clipPath: toDark ? ['inset(0 0 100% 0)', 'inset(0)'] : ['inset(100% 0 0 0)', 'inset(0)']},
        {duration: 280, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)', pseudoElement: '::view-transition-new(root)'},
      )
    })
  }

  return (
    <button
      type="button"
      onClick={cycleMode}
      aria-label={`当前${LABEL[mode]}，点击切换为${LABEL[nextMode]}`}
      className="inline-flex h-9 items-center gap-1.5 rounded-[10px] px-3 text-sm text-muted hover:bg-lift hover:text-ink"
    >
      <Icon size={18} strokeWidth={1.8} />
      <span className="hidden sm:inline">{SHORT[mode]}</span>
    </button>
  )
}
