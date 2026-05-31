import {createContext, useContext, useMemo, useState} from 'react'
import type {ReactNode} from 'react'
import {CheckCircle2, Copy, Info, X, XCircle} from 'lucide-react'

type ToastType = 'success' | 'error' | 'info'

interface Toast {
  id: number
  type: ToastType
  title: string
  message?: string
}

interface ToastOptions {
  autoClose?: boolean
}

interface ToastContextValue {
  success: (title: string, message?: string, options?: ToastOptions) => void
  error: (title: string, message?: string, options?: ToastOptions) => void
  info: (title: string, message?: string, options?: ToastOptions) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const icons = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
}

export function ToastProvider({children}: {children: ReactNode}) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const remove = (id: number) => setToasts((current) => current.filter((toast) => toast.id !== id))
  const push = (type: ToastType, title: string, message?: string, options?: ToastOptions) => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, {id, type, title, message}])
    // 提示默认常驻，等用户主动关闭；如显式传 autoClose: true 才走定时关闭。
    if (options?.autoClose === true) {
      const duration = type === 'success' ? 6000 : 4000
      window.setTimeout(() => remove(id), duration)
    }
  }
  const value = useMemo<ToastContextValue>(() => ({
    success: (title, message, options) => push('success', title, message, options),
    error: (title, message, options) => push('error', title, message, options),
    info: (title, message, options) => push('info', title, message, options),
  }), [])

  // 可见上限 3 条；超出的折叠（取最新 3 条，旧的合并成「+N 条更早」角标）
  const VISIBLE_LIMIT = 3
  const visible = toasts.slice(-VISIBLE_LIMIT)
  const hiddenCount = toasts.length - visible.length
  const clearOlder = () => setToasts((current) => current.slice(-VISIBLE_LIMIT))

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/*
        移动端 bottom-center，桌面端右上角：
        - 手机：贴底，拇指能直接关；不挡顶部主内容
        - 桌面：维持原 top-right
        毛玻璃 + 半透明 bg-panel/80 + backdrop-blur，叠在内容上也能透视
      */}
      <div
        data-toast-stack
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col gap-2 sm:inset-x-auto sm:bottom-auto sm:right-4 sm:top-4 sm:w-[calc(100vw-2rem)] sm:max-w-sm sm:gap-3 [&>*]:pointer-events-auto"
      >
        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={clearOlder}
            className="self-center rounded-full border border-line bg-panel/80 px-3 py-1 text-xs text-muted shadow-card backdrop-blur transition hover:bg-panel"
          >
            清掉更早的 {hiddenCount} 条
          </button>
        )}
        {visible.map((toast) => {
          const Icon = icons[toast.type]
          const copyText = [toast.title, toast.message].filter(Boolean).join('\n')
          return (
            <div key={toast.id} className={`animate-pop overflow-hidden rounded-2xl border bg-panel/85 p-4 shadow-card backdrop-blur-md ${
              toast.type === 'error' ? 'border-danger/40' : toast.type === 'success' ? 'border-success/40' : 'border-line'
            }`}>
              <div className="flex gap-3">
                <Icon size={20} className={`shrink-0 ${toast.type === 'error' ? 'text-danger' : toast.type === 'success' ? 'text-success' : 'text-brand'}`} />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-ink">{toast.title}</p>
                  {toast.message && <p className="mt-1 break-words text-sm leading-5 text-muted">{toast.message}</p>}
                </div>
                <button type="button" aria-label="关闭提示" onClick={() => remove(toast.id)} className="grid h-8 w-8 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95">
                  <X size={16} />
                </button>
              </div>
              {toast.type === 'error' && (
                <button type="button" onClick={() => navigator.clipboard.writeText(copyText)} className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-xl bg-lift px-3 text-sm text-muted transition hover:bg-line/70 active:scale-95">
                  <Copy size={14} />
                  复制错误
                </button>
              )}
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used inside ToastProvider')
  }
  return context
}
