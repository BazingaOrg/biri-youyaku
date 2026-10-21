import {Loader2} from 'lucide-react'
import {Rabbit} from './Rabbit'

/** 统一的品牌色加载转圈。 */
export function Spinner({size = 18, className = ''}: {size?: number; className?: string}) {
  return <Loader2 size={size} className={`animate-spin text-brand ${className}`} aria-hidden />
}

/** 整页加载：兔子缩进书里再探出来，可选文案。按钮里的小转圈仍用 Spinner。 */
export function PageLoading({label}: {label?: string}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="grid place-items-center gap-3 py-16 text-sm text-muted"
    >
      <Rabbit mood="loading" className="h-28 w-28" />
      {label && <p>{label}</p>}
    </div>
  )
}
