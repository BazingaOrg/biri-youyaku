import {createContext, useContext, useMemo, useState} from 'react'
import type {ReactNode} from 'react'
import {CheckCircle2, Copy, Info, Undo2, X, XCircle} from 'lucide-react'

const POP_OUT_FALLBACK_MS = 200 // pop-out 150ms + 50ms 余量；改动画时长时同步改这里

type ToastType = 'success' | 'error' | 'info'

interface ToastAction {
  label: string
  onClick: () => void
}

interface Toast {
  id: number
  type: ToastType
  title: string
  message?: string
  taskName?: string
  action?: ToastAction
  closing?: boolean
}

interface ToastOptions {
  autoClose?: boolean
  // 绑定到具体任务的提示（如「总结完成」「下载音频」），传入后会作为副标题展示，
  // 过长以省略号截断。不传则只显示 title / message。
  taskName?: string
  // 行内动作按钮（如删除后的「撤销」）。传入即视为限时提示，到点自动关闭。
  action?: ToastAction
  // 自定义自动关闭时长（毫秒）。autoClose / action 任一存在时生效。
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
    setToasts((current) => [...current, {id, type, title, message, taskName: options?.taskName, action: options?.action}])
    // 提示默认常驻，等用户主动关闭；autoClose 或带 action（如撤销）时走定时关闭。
    if (options?.autoClose === true || options?.action) {
      const duration = options?.durationMs ?? (type === 'success' ? 6000 : 4000)
      window.setTimeout(() => startClose(id), duration)
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
            <div
              key={toast.id}
              onAnimationEnd={() => {
                if (toast.closing) remove(toast.id)
              }}
              className={`${toast.closing ? 'animate-pop-out' : 'animate-pop'} overflow-hidden rounded-2xl border bg-panel/85 p-4 shadow-card backdrop-blur-md ${
              toast.type === 'error' ? 'border-danger/40' : toast.type === 'success' ? 'border-success/40' : 'border-line'
            }`}>
              {/*
                items-start + icon/按钮分别配 mt-0.5 / -mt-1：
                让 20px 图标的视觉中线对齐 title 首行文字中线，关闭按钮也不再"漂"在右上方。
              */}
              <div className="flex items-start gap-3">
                <Icon size={20} className={`mt-0.5 shrink-0 ${toast.type === 'error' ? 'text-danger' : toast.type === 'success' ? 'text-success' : 'text-brand'}`} />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold leading-6 text-ink">{toast.title}</p>
                  {toast.taskName && (
                    // 任务名做副标题：单行截断，hover 时 title attribute 给出完整名
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
