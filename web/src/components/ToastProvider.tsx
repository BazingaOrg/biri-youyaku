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
    const shouldAutoClose = options?.autoClose ?? type !== 'error'
    if (shouldAutoClose) {
      window.setTimeout(() => remove(id), 4000)
    }
  }
  const value = useMemo<ToastContextValue>(() => ({
    success: (title, message, options) => push('success', title, message, options),
    error: (title, message, options) => push('error', title, message, options),
    info: (title, message, options) => push('info', title, message, options),
  }), [])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed right-4 top-4 z-50 grid w-[calc(100vw-2rem)] max-w-sm gap-3">
        {toasts.map((toast) => {
          const Icon = icons[toast.type]
          const copyText = [toast.title, toast.message].filter(Boolean).join('\n')
          return (
            <div key={toast.id} className={`animate-pop rounded-2xl border bg-panel/95 p-4 shadow-card backdrop-blur ${
              toast.type === 'error' ? 'border-danger/20' : toast.type === 'success' ? 'border-success/20' : 'border-line'
            }`}>
              <div className="flex gap-3">
                <Icon size={20} className={toast.type === 'error' ? 'text-danger' : toast.type === 'success' ? 'text-success' : 'text-brand'} />
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
