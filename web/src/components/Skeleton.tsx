/** 单根骨架条：灰底 + 呼吸动效，配色/圆角对齐现有设计 token。 */
export function SkeletonLine({className = ''}: {className?: string}) {
  return <div className={`animate-pulse rounded-2xl bg-lift ${className}`} />
}

/** 列表首屏骨架屏：按 count 重复渲染同款条目，替代居中转圈的过渡态。 */
export function Skeleton({count = 4, className = ''}: {count?: number; className?: string}) {
  return (
    <div className={`grid gap-2 ${className}`} aria-hidden>
      {Array.from({length: count}, (_, i) => (
        <SkeletonLine key={i} className="h-16 w-full" />
      ))}
    </div>
  )
}
