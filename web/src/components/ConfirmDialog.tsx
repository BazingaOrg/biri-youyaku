import {useEffect, useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {POP_OUT_FALLBACK_MS} from '../lib/animation'

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
  /** 除 loading 外的禁用条件（例如表单输入未通过校验）。 */
  confirmDisabled?: boolean
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
  confirmDisabled = false,
  onConfirm,
  onSecondary,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)
  const onCancelRef = useRef(onCancel)
  const loadingRef = useRef(loading)
  const focusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  onCancelRef.current = onCancel
  loadingRef.current = loading

  const [closing, setClosing] = useState(false)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wasOpenRef = useRef(open)
  // open 刚变为 false 的那一帧仍保留 DOM，避免焦点陷阱和退场动画之间出现空档。
  const rendered = open || closing || wasOpenRef.current

  useEffect(() => {
    if (open === wasOpenRef.current) return

    if (open) {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current)
        closeTimerRef.current = null
      }
      setClosing(false)
      previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      focusTimerRef.current = window.setTimeout(() => {
        focusTimerRef.current = null
        ;(cancelButtonRef.current ?? dialogRef.current)?.focus()
      }, 0)
      return
    }

    setClosing(true)
    closeTimerRef.current = setTimeout(() => setClosing(false), POP_OUT_FALLBACK_MS)
  }, [open])

  useEffect(() => {
    wasOpenRef.current = open
  }, [open])

  useEffect(() => {
    if (rendered) return
    previouslyFocusedRef.current?.focus()
    previouslyFocusedRef.current = null
  }, [rendered])

  useEffect(() => {
    if (!rendered) return

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !loadingRef.current) onCancelRef.current()
      if (event.key !== 'Tab') return
      const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [])]
      if (focusable.length === 0) {
        event.preventDefault()
        dialogRef.current?.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [rendered])

  useEffect(() => () => {
    if (focusTimerRef.current) clearTimeout(focusTimerRef.current)
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current)
  }, [])

  const endClosing = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current)
      closeTimerRef.current = null
    }
    setClosing(false)
  }

  if (!rendered) return null

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
        className={`absolute inset-0 cursor-default bg-ink/30 backdrop-blur-sm transition-opacity duration-150 ${
          closing ? 'opacity-0' : 'opacity-100'
        }`}
      />
      <div
        ref={dialogRef}
        tabIndex={-1}
        onAnimationEnd={() => {
          if (closing) endClosing()
        }}
        className={`${closing ? 'animate-pop-out' : 'animate-pop'} relative flex max-h-[calc(100dvh-2rem)] w-full max-w-sm flex-col overflow-hidden rounded-2xl border border-line bg-panel/95 shadow-cardHover backdrop-blur-md`}
      >
        <div className="shrink-0 px-5 pt-5">
          <h2 id="confirm-dialog-title" className="text-base font-semibold text-ink">{title}</h2>
        </div>
        {/* div 而非 p：调用方偶尔需要塞输入框等块级元素（如蒸馏确认层的数量输入），
            p 标签会被浏览器强制截断成非法嵌套。 */}
        {description && <div className="min-h-0 overflow-y-auto px-5 pt-2 text-sm leading-6 text-muted">{description}</div>}
        <div className="mt-4 flex shrink-0 flex-wrap justify-end gap-2 border-t border-line/70 px-5 py-4">
          <button
            type="button"
            ref={cancelButtonRef}
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
            disabled={loading || confirmDisabled}
            className={`inline-flex min-h-10 items-center rounded-xl px-4 text-sm font-medium shadow-card transition-[transform,filter] hover:brightness-105 active:scale-95 disabled:opacity-50 ${
              danger ? 'bg-dangerSolid text-onDanger' : 'bg-brandSolid text-onBrand'
            }`}
          >
            {loading ? '处理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
