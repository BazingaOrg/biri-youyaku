import type {ReactNode} from 'react'

type Variant = 'ghost' | 'primary' | 'danger'

interface IconButtonProps {
  icon: ReactNode
  label: string
  onClick?: () => void
  disabled?: boolean
  variant?: Variant
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_CLASS: Record<NonNullable<IconButtonProps['size']>, string> = {
  sm: 'h-10 w-10',
  md: 'h-11 w-11',
  lg: 'h-14 w-14',
}

const VARIANT_CLASS: Record<Variant, string> = {
  ghost:
    'bg-lift text-muted hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-40',
  primary:
    'bg-brand text-white hover:brightness-105 active:scale-95 disabled:opacity-50',
  danger:
    'bg-danger/10 text-danger hover:bg-danger/15 active:scale-95 disabled:opacity-40',
}

/**
 * 图标按钮 + hover 显示文字 tooltip。
 * tooltip 用纯 CSS，无 JS 库：group-hover 显示，pointer-events-none 不影响点击。
 */
export function IconButton({
  icon,
  label,
  onClick,
  disabled,
  variant = 'ghost',
  size = 'md',
}: IconButtonProps) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={label}
        title={label}
        onClick={onClick}
        disabled={disabled}
        className={`grid place-items-center rounded-2xl transition disabled:cursor-not-allowed ${SIZE_CLASS[size]} ${VARIANT_CLASS[variant]}`}
      >
        {icon}
      </button>
      <span className="pointer-events-none absolute left-1/2 top-full z-10 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-xs font-medium text-canvas opacity-0 shadow-card transition group-hover:opacity-100 group-focus-within:opacity-100">
        {label}
      </span>
    </span>
  )
}
