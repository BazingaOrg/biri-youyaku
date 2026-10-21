import type {ReactNode} from 'react'
import {Link} from 'wouter'

interface ChipProps {
  children: ReactNode
  href?: string
  onRemove?: () => void
  removeLabel?: string
}

export function Chip({children, href, onRemove, removeLabel = '移除'}: ChipProps) {
  const className =
    'inline-flex max-w-full items-center gap-1 rounded-full bg-lift px-2.5 py-1 text-[13px] text-brand'
  const inner = (
    <>
      <span className="min-w-0 truncate">{children}</span>
      {onRemove ? (
        <button
          type="button"
          aria-label={removeLabel}
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
            onRemove()
          }}
          className="grid h-5 w-5 place-items-center rounded-full text-base leading-none text-muted hover:text-ink"
        >
          ×
        </button>
      ) : null}
    </>
  )
  if (href) {
    return (
      <Link href={href} className={className}>
        {inner}
      </Link>
    )
  }
  return <span className={className}>{inner}</span>
}
