import {useEffect, useState} from 'react'

type ThemeMode = 'system' | 'light' | 'dark'

// TS 自带 lib 还没有 View Transitions 类型
declare global {
  interface Document {
    startViewTransition?: (update: () => void) => {ready: Promise<void>}
  }
}

const STORAGE_KEY = 'theme'
const ORDER: ThemeMode[] = ['system', 'light', 'dark']
const LABEL: Record<ThemeMode, string> = {
  system: '主题：跟随系统',
  light: '主题：白天',
  dark: '主题：黑夜',
}
const THEME_COLOR: Record<'light' | 'dark', string> = {
  light: '#E26A8D',
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
  // 两个 theme-color meta 都写成当前色，地址栏颜色不再受系统偏好绑架。
  document
    .querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
    .forEach((meta) => (meta.content = THEME_COLOR[resolved]))
}

/**
 * 右上角三档主题切换：跟随系统 → 白天 → 黑夜循环。
 * 图标交叉旋转渐变；明暗切换用落幕/升幕动画（View Transitions，
 * 不支持或 reduced-motion 时直接切换）。
 */
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

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length]
    try {
      if (next === 'system') window.localStorage.removeItem(STORAGE_KEY)
      else window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // 存不了就只在本次会话生效
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
      // setMode 是异步的，视图快照需要同步落 DOM
      applyResolved(resolve(next))
      commit()
    })
    void transition.ready.then(() => {
      document.documentElement.animate(
        {clipPath: toDark ? ['inset(0 0 100% 0)', 'inset(0)'] : ['inset(100% 0 0 0)', 'inset(0)']},
        {duration: 520, easing: 'cubic-bezier(0.65, 0, 0.35, 1)', pseudoElement: '::view-transition-new(root)'},
      )
    })
  }

  const iconClass = (active: boolean) =>
    `absolute inset-0 m-auto h-5 w-5 transition-all duration-300 ease-out ${
      active ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-50 opacity-0'
    }`

  return (
    <div className="group fixed right-4 top-4 z-40 sm:right-6 sm:top-6">
      <button
        type="button"
        onClick={cycle}
        aria-label={LABEL[mode]}
        className="relative flex h-10 w-10 items-center justify-center rounded-full border border-line bg-panel/80 text-muted shadow-card backdrop-blur transition-colors hover:text-ink active:scale-95"
      >
        {/* 跟随系统：半染圆 */}
        <svg viewBox="0 0 24 24" className={iconClass(mode === 'system')} fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="8" />
          <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none" />
        </svg>
        {/* 白天：朝阳 */}
        <svg viewBox="0 0 24 24" className={iconClass(mode === 'light')} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.5 5.5l1.4 1.4M17.1 17.1l1.4 1.4M18.5 5.5l-1.4 1.4M6.9 17.1l-1.4 1.4" />
        </svg>
        {/* 黑夜：弦月 */}
        <svg viewBox="0 0 24 24" className={iconClass(mode === 'dark')} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
          <path d="M12 3.5a6.5 6.5 0 0 0 8.5 8.5A8.5 8.5 0 1 1 12 3.5Z" />
        </svg>
      </button>
      <span className="pointer-events-none absolute right-0 top-full mt-2 whitespace-nowrap rounded-lg bg-ink px-2 py-1 text-xs text-canvas opacity-0 transition-opacity group-hover:opacity-100">
        {LABEL[mode]}
      </span>
    </div>
  )
}
