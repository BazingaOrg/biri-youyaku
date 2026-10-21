import {forwardRef} from 'react'
import type {ButtonHTMLAttributes, ReactNode} from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
export type ButtonSize = 'md' | 'sm'

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    'bg-brandSolid text-onBrand shadow-card hover:brightness-105 disabled:opacity-50',
  secondary:
    'border border-line bg-panel text-ink hover:bg-lift disabled:opacity-50',
  ghost: 'bg-transparent text-muted hover:bg-lift hover:text-ink disabled:opacity-40',
}

const SIZE: Record<ButtonSize, string> = {
  md: 'min-h-11 rounded-xl px-4 text-sm',
  sm: 'min-h-8 rounded-[10px] px-3 text-[13px]',
}

export function buttonClassName({
  variant = 'secondary',
  size = 'md',
  className = '',
}: {
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
} = {}) {
  return `inline-flex w-fit max-w-full items-center justify-center gap-1.5 whitespace-nowrap font-medium transition-[transform,background-color,color,filter] active:scale-[0.98] disabled:cursor-not-allowed ${VARIANT[variant]} ${SIZE[size]} ${className}`
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    className = '',
    type = 'button',
    children,
    ...props
  },
  ref,
) {
  return (
    <button ref={ref} type={type} className={buttonClassName({variant, size, className})} {...props}>
      {children}
    </button>
  )
})
