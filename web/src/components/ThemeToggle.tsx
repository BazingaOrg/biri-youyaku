import {useEffect, useRef, useState} from 'react'
import {Check, Monitor, Moon, Sun} from 'lucide-react'

type ThemeMode = 'system' | 'light' | 'dark'

// TS 自带 lib 还没有 View Transitions 类型
declare global {
  interface Document {
    startViewTransition?: (update: () => void) => {ready: Promise<void>}
  }
}

const STORAGE_KEY = 'theme'
const LABEL: Record<ThemeMode, string> = {
  system: '跟随系统',
  light: '白天',
  dark: '黑夜',
}
const THEME_COLOR: Record<'light' | 'dark', string> = {
  light: '#B33F66',
  dark: '#15131A',
}

function readMode(): ThemeMode {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw === 'light' || raw === 'dark' ? raw : 'system'
  } catch {
    return 'system'
  }
}

function resolve(mode: ThemeMode): 'light' | 'dark' {
  if (mode !== 'system') return mode
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyResolved(resolved: 'light' | 'dark') {
  document.documentElement.dataset.theme = resolved
  document
    .querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
    .forEach((meta) => (meta.content = THEME_COLOR[resolved]))
}

export function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>(readMode)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    applyResolved(resolve(mode))
    if (mode !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyResolved(resolve('system'))
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [mode])

  useEffect(() => {
    if (!open) return
    const closeOnOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', closeOnOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  const selectMode = (next: ThemeMode, restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) window.requestAnimationFrame(() => triggerRef.current?.focus())
    if (next === mode) return
    try {
      if (next === 'system') window.localStorage.removeItem(STORAGE_KEY)
      else window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
    }

    const commit = () => setMode(next)
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const willChange = resolve(next) !== resolve(mode)
    if (!willChange || reduceMotion || !document.startViewTransition) {
      commit()
      return
    }

    // 落幕/升幕：入夜像夜幕自上而下落下，回到白天像幕布自下而上升起
    const toDark = resolve(next) === 'dark'
    const transition = document.startViewTransition(() => {
      applyResolved(resolve(next))
      commit()
    })
    void transition.ready.then(() => {
      document.documentElement.animate(
        {clipPath: toDark ? ['inset(0 0 100% 0)', 'inset(0)'] : ['inset(100% 0 0 0)', 'inset(0)']},
        {duration: 280, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)', pseudoElement: '::view-transition-new(root)'},
      )
    })
  }

  const iconClass = (active: boolean) =>
    `absolute inset-0 m-auto h-5 w-5 transition-[transform,opacity] duration-200 ease-out ${
      active ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-50 opacity-0'
    }`

  const options: Array<{value: ThemeMode; icon: typeof Monitor}> = [
    {value: 'system', icon: Monitor},
    {value: 'light', icon: Sun},
    {value: 'dark', icon: Moon},
  ]

  return (
    <div ref={rootRef} className="group relative">
      {open && (
        <div className="absolute bottom-full right-0 mb-2 grid w-36 gap-1 rounded-2xl border border-line/70 bg-panel/95 p-1.5 shadow-card backdrop-blur" aria-label="主题选项">
          {options.map(({value, icon: OptionIcon}) => (
            <button
              key={value}
              type="button"
              onClick={(event) => selectMode(value, event.detail === 0)}
              aria-pressed={mode === value}
              className={`flex min-h-9 items-center gap-2 rounded-xl px-2.5 text-left text-sm transition-colors ${
                mode === value ? 'bg-brandSoft text-brand' : 'text-muted hover:bg-lift hover:text-ink'
              }`}
            >
              <OptionIcon size={16} />
              <span className="flex-1">{LABEL[value]}</span>
              {mode === value && <Check size={14} />}
            </button>
          ))}
        </div>
      )}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={`选择主题，当前${LABEL[mode]}`}
        aria-haspopup="true"
        aria-expanded={open}
        className="relative flex h-11 w-11 items-center justify-center rounded-full border border-line bg-panel/80 text-muted shadow-card backdrop-blur transition-[transform,color,background-color] duration-150 ease-out hover:text-ink active:scale-[0.96]"
      >
        <svg viewBox="0 0 24 24" className={iconClass(mode === 'system')} fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="8" />
          <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none" />
        </svg>
        <svg viewBox="0 0 24 24" className={iconClass(mode === 'light')} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.5 5.5l1.4 1.4M17.1 17.1l1.4 1.4M18.5 5.5l-1.4 1.4M6.9 17.1l-1.4 1.4" />
        </svg>
        <svg viewBox="0 0 24 24" className={iconClass(mode === 'dark')} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
          <path d="M12 3.5a6.5 6.5 0 0 0 8.5 8.5A8.5 8.5 0 1 1 12 3.5Z" />
        </svg>
      </button>
      {!open && (
        <span className="pointer-events-none absolute bottom-full right-0 mb-2 whitespace-nowrap rounded-lg bg-ink px-2 py-1 text-xs text-canvas opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          主题：{LABEL[mode]}
        </span>
      )}
    </div>
  )
}
