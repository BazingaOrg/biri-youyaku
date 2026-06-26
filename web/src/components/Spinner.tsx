import {Loader2} from 'lucide-react'

/** 统一的品牌色加载转圈。 */
export function Spinner({size = 18, className = ''}: {size?: number; className?: string}) {
  return <Loader2 size={size} className={`animate-spin text-brand ${className}`} aria-hidden />
}

/** 整页/整块的居中加载态：转圈 + 可选文案。用于详情加载、恢复、解析等过渡场景。 */
export function PageLoading({label}: {label?: string}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="grid place-items-center gap-3 py-16 text-sm text-muted"
    >
      <Spinner size={26} />
      {label && <p>{label}</p>}
    </div>
  )
}
