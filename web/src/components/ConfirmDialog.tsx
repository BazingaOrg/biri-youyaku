import {AlertTriangle, X} from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-ink/30 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-[420px] rounded-[28px] bg-white p-6 shadow-bili animate-pop">
        <button type="button" aria-label="关闭弹窗" onClick={onCancel} className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-full text-muted transition hover:bg-lift active:scale-95">
          <X size={17} />
        </button>
        <div className="grid justify-items-center text-center">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-pink/10 text-pink">
            <AlertTriangle size={22} />
          </span>
          <h2 className="mt-4 text-lg font-semibold">{title}</h2>
          <p className="mt-2 max-w-[320px] text-sm leading-6 text-muted">{description}</p>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-3">
          <button type="button" onClick={onCancel} disabled={loading} className="min-h-11 rounded-2xl bg-lift px-4 text-sm font-medium text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-50">
            取消
          </button>
          <button type="button" onClick={onConfirm} disabled={loading} className="min-h-11 rounded-2xl bg-pink px-4 text-sm font-semibold text-white shadow-bili transition hover:brightness-105 active:scale-95 disabled:opacity-50">
            {loading ? '处理中...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
