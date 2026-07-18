import {useEffect} from 'react'
import type {ReactNode} from 'react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  secondaryLabel?: string
  /** 危险操作（删除 / 清空）时确认按钮走 danger 配色。 */
  danger?: boolean
  /** 确认动作进行中：禁用按钮、确认文案可加 loading 态。 */
  loading?: boolean
  onConfirm: () => void
  onSecondary?: () => void
  onCancel: () => void
}

/**
 * 应用内确认弹窗，替代原生 window.confirm，沿用项目 panel / rounded-2xl / animate-pop 风格。
 * Esc 取消、点遮罩取消、明暗跟随系统。
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  cancelLabel = '取消',
  secondaryLabel,
  danger = false,
  loading = false,
  onConfirm,
  onSecondary,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !loading) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, loading, onCancel])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <button
        type="button"
        aria-label="关闭"
        tabIndex={-1}
        onClick={() => !loading && onCancel()}
        className="absolute inset-0 cursor-default bg-ink/30 backdrop-blur-sm"
      />
      <div className="animate-pop relative w-full max-w-sm rounded-2xl border border-line bg-panel/95 p-5 shadow-cardHover backdrop-blur-md">
        <h2 id="confirm-dialog-title" className="text-base font-semibold text-ink">
          {title}
        </h2>
        {/* div 而非 p：调用方偶尔需要塞输入框等块级元素（如蒸馏确认层的数量输入），
            p 标签会被浏览器强制截断成非法嵌套。 */}
        {description && <div className="mt-2 text-sm leading-6 text-muted">{description}</div>}
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="inline-flex min-h-10 items-center rounded-xl bg-lift px-4 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-40"
          >
            {cancelLabel}
          </button>
          {secondaryLabel && onSecondary && (
            <button
              type="button"
              onClick={onSecondary}
              disabled={loading}
              className="inline-flex min-h-10 items-center rounded-xl bg-lift px-4 text-sm font-medium text-ink transition-[transform,background-color,color] hover:bg-line/70 active:scale-95 disabled:opacity-40"
            >
              {secondaryLabel}
            </button>
          )}
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`inline-flex min-h-10 items-center rounded-xl px-4 text-sm font-medium text-white shadow-card transition-[transform,filter] hover:brightness-105 active:scale-95 disabled:opacity-50 ${
              danger ? 'bg-danger' : 'bg-brand'
            }`}
          >
            {loading ? '处理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
