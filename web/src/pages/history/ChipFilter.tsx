import {useState} from 'react'
import {Tag} from 'lucide-react'

interface ChipFilterItem {
  key: string
  label: string
  count: number
}

export function ChipFilter({
  label,
  items,
  selected,
  total,
  onSelect,
  variant = 'neutral',
}: {
  label: string
  items: ChipFilterItem[]
  selected: string | null
  total?: number
  onSelect: (value: string | null) => void
  variant?: 'neutral' | 'tag'
}) {
  const [expanded, setExpanded] = useState(false)
  const shouldCollapse = items.length > 6
  const itemClass = (active: boolean) => {
    if (active) return 'bg-brand text-white shadow-card'
    if (variant === 'tag') return 'bg-brandSoft/50 text-brand hover:bg-brandSoft'
    return 'bg-lift text-muted hover:bg-line/70 hover:text-ink'
  }

  return (
    <div className="grid gap-2 border-b border-line/60 py-3" aria-label={`${label}筛选`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-1.5 text-xs font-medium text-muted">
          {variant === 'tag' && <Tag size={13} className="shrink-0" />}
          <span>{label}</span>
        </div>
        {shouldCollapse && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="shrink-0 rounded-full px-2 py-1 text-xs text-muted transition-[transform,color,background-color] hover:bg-lift hover:text-ink active:scale-95"
          >
            {expanded ? '收起' : `展开全部（${items.length}）`}
          </button>
        )}
      </div>
      <div className={`relative ${shouldCollapse && !expanded ? 'max-h-[4.5rem] overflow-hidden' : ''}`}>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onSelect(null)}
            className={`inline-flex min-h-8 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-[transform,background-color,color] active:scale-95 ${itemClass(selected == null)}`}
          >
            全部
            {total != null && (
              <span className={selected == null ? 'text-white/80' : 'text-muted'}>{total}</span>
            )}
          </button>
          {items.map((item) => {
            const active = selected === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => onSelect(active ? null : item.key)}
                className={`inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-[transform,background-color,color] active:scale-95 ${itemClass(active)}`}
                title={`${item.label} · ${item.count}`}
              >
                <span className="truncate">{item.label}</span>
                <span className={active ? 'text-white/80' : variant === 'tag' ? 'text-brand/60' : 'text-muted'}>
                  {item.count}
                </span>
              </button>
            )
          })}
        </div>
        {shouldCollapse && !expanded && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-canvas to-transparent" />
        )}
      </div>
    </div>
  )
}
