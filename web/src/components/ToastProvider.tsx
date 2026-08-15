import {createContext, useContext, useMemo, useState} from 'react'
import type {ReactNode} from 'react'
import {CheckCircle2, Copy, Info, Undo2, X, XCircle} from 'lucide-react'
import {POP_OUT_FALLBACK_MS} from '../lib/animation'

type ToastType = 'success' | 'error' | 'info'

interface ToastAction {
  label: string
  onClick: () => void
}

interface Toast {
  id: number
  dedupeKey?: string
  type: ToastType
  title: string
  message?: string
  taskName?: string
  action?: ToastAction
  closing?: boolean
}

interface ToastOptions {
  autoClose?: boolean
  dedupeKey?: string
  taskName?: string
  action?: ToastAction
  durationMs?: number
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
  const startClose = (id: number) => {
    setToasts((current) => {
      const toast = current.find((t) => t.id === id)
      if (!toast || toast.closing) return current
      return current.map((t) => (t.id === id ? {...t, closing: true} : t))
    })
    window.setTimeout(() => remove(id), POP_OUT_FALLBACK_MS)
  }
  const push = (type: ToastType, title: string, message?: string, options?: ToastOptions) => {
    const id = Date.now() + Math.random()
    const nextToast = {id, type, title, message, dedupeKey: options?.dedupeKey, taskName: options?.taskName, action: options?.action}
    setToasts((current) => [
      ...current.filter((toast) => !options?.dedupeKey || toast.dedupeKey !== options.dedupeKey),
      nextToast,
    ])
    const shouldAutoClose = options?.autoClose ?? (options?.action != null || type !== 'error')
    if (shouldAutoClose) {
      const defaultDuration = options?.action ? (type === 'success' ? 6000 : 4000) : (type === 'success' ? 6000 : 5500)
      const duration = options?.durationMs ?? defaultDuration
      window.setTimeout(() => startClose(id), duration)
    }
  }
  const value = useMemo<ToastContextValue>(() => ({
    success: (title, message, options) => push('success', title, message, options),
    error: (title, message, options) => push('error', title, message, options),
    info: (title, message, options) => push('info', title, message, options),
  }), [])

  const VISIBLE_LIMIT = 3
  const visible = toasts.slice(-VISIBLE_LIMIT)
  const clearAll = () => {
    const ids = new Set(toasts.map((toast) => toast.id))
    setToasts((current) => current.map((toast) => ids.has(toast.id) ? {...toast, closing: true} : toast))
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => !ids.has(toast.id)))
    }, POP_OUT_FALLBACK_MS)
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        data-toast-stack
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col gap-2 sm:inset-x-auto sm:bottom-auto sm:right-4 sm:top-4 sm:w-[calc(100vw-2rem)] sm:max-w-sm sm:gap-3 [&>*]:pointer-events-auto"
      >
        {toasts.length > 1 && (
          <button
            type="button"
            onClick={clearAll}
            aria-label={`全部清除 ${toasts.length} 条通知`}
            className="self-center rounded-full border border-line bg-panel/80 px-3 py-1 text-xs text-muted shadow-card backdrop-blur transition hover:bg-panel"
          >
            全部清除（{toasts.length}）
          </button>
        )}
        {visible.map((toast) => {
          const Icon = icons[toast.type]
          const copyText = [toast.title, toast.message].filter(Boolean).join('\n')
          return (
            <div
              key={toast.id}
              role={toast.type === 'error' ? 'alert' : 'status'}
              aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
              aria-atomic="true"
              onAnimationEnd={() => {
                if (toast.closing) remove(toast.id)
              }}
              className={`${toast.closing ? 'animate-pop-out' : 'animate-pop'} overflow-hidden rounded-2xl border bg-panel/85 p-4 shadow-card backdrop-blur-md ${
              toast.type === 'error' ? 'border-danger/40' : toast.type === 'success' ? 'border-success/40' : 'border-line'
            }`}>
              <div className="flex items-start gap-3">
                <Icon size={20} className={`mt-0.5 shrink-0 ${toast.type === 'error' ? 'text-danger' : toast.type === 'success' ? 'text-success' : 'text-brand'}`} />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold leading-6 text-ink">{toast.title}</p>
                  {toast.taskName && (
                    <p className="mt-0.5 truncate text-xs leading-5 text-muted/80" title={toast.taskName}>
                      {toast.taskName}
                    </p>
                  )}
                  {toast.message && <p className="mt-1 break-words text-sm leading-5 text-muted">{toast.message}</p>}
                </div>
                <button type="button" aria-label="关闭提示" onClick={() => startClose(toast.id)} className="-mr-1 -mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95">
                  <X size={16} />
                </button>
              </div>
              {toast.action && (
                <button
                  type="button"
                  onClick={() => {
                    toast.action?.onClick()
                    startClose(toast.id)
                  }}
                  className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-xl bg-lift px-3 text-sm font-medium text-brand transition hover:bg-brandSoft/60 active:scale-95"
                >
                  <Undo2 size={14} />
                  {toast.action.label}
                </button>
              )}
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
