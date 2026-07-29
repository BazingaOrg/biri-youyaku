import {useEffect, useRef} from 'react'

function level(count: number): number {
  if (count <= 0) return 0
  if (count === 1) return 1
  if (count === 2) return 2
  if (count <= 4) return 3
  return 4
}

function fillFor(count: number): string {
  const levels = [
    'var(--color-bg-sunken)',
    'color-mix(in srgb, var(--color-brand) 28%, var(--color-bg-elevated))',
    'color-mix(in srgb, var(--color-brand) 46%, var(--color-bg-elevated))',
    'color-mix(in srgb, var(--color-brand) 68%, var(--color-bg-elevated))',
    'var(--color-brand)',
  ]
  return levels[level(count)]
}

function weekRangeLabel(weekStart: number): string {
  const start = new Date(weekStart)
  const end = new Date(weekStart)
  end.setDate(end.getDate() + 6)
  const formatter = new Intl.DateTimeFormat('zh-CN', {month: 'numeric', day: 'numeric'})
  return `${formatter.format(start)}—${formatter.format(end)}`
}

export interface WeekNavigatorItem {
  weekStart: number
  count: number
}

export function WeekNavigator({
  weeks,
  selectedWeek,
  onSelect,
}: {
  weeks: WeekNavigatorItem[]
  selectedWeek: number | null
  onSelect: (weekStart: number) => void
}) {
  // Newest first in data; reverse for left→right chronological scroll.
  const chronological = [...weeks].sort((a, b) => a.weekStart - b.weekStart)
  const maxCount = Math.max(1, ...chronological.map((week) => week.count))
  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const selectedRef = useRef<HTMLButtonElement | null>(null)

  // Scroll only the strip so selecting via ‹ › or load-more keeps the week visible.
  useEffect(() => {
    const scroller = scrollerRef.current
    const node = selectedRef.current
    if (!scroller || !node) return
    const target = node.offsetLeft - scroller.clientWidth / 2 + node.offsetWidth / 2
    scroller.scrollTo({left: Math.max(0, target), behavior: 'smooth'})
  }, [selectedWeek, chronological.length])

  let lastLabelKey = ''

  return (
    <div className="relative">
      <div
        ref={scrollerRef}
        className="overflow-x-auto overscroll-x-contain scroll-smooth pb-1 [scrollbar-width:thin]"
      >
        <div
          className="flex min-w-min snap-x snap-mandatory items-end gap-1 px-0.5 py-1"
          role="list"
          aria-label="按周浏览，可横向滑动；下方按钮也可切换"
        >
          {chronological.map((week) => {
            const date = new Date(week.weekStart)
            const year = date.getFullYear()
            const month = date.getMonth() + 1
            const labelKey = `${year}-${month}`
            const showLabel = labelKey !== lastLabelKey
            if (showLabel) lastLabelKey = labelKey
            // Cross-year: show "2025年3月" once at the boundary so long histories stay oriented.
            const currentYear = new Date().getFullYear()
            const monthText = year !== currentYear ? `${year}年${month}月` : `${month}月`
            const selected = selectedWeek === week.weekStart
            const height = 12 + Math.round((week.count / maxCount) * 22)
            return (
              <div
                key={week.weekStart}
                className="relative flex w-9 shrink-0 snap-center flex-col items-center"
                role="listitem"
              >
                {showLabel && (
                  <span className="absolute -top-4 left-1/2 z-[1] -translate-x-1/2 whitespace-nowrap text-[10px] text-muted">
                    {monthText}
                  </span>
                )}
                <button
                  ref={selected ? selectedRef : undefined}
                  type="button"
                  aria-label={`${weekRangeLabel(week.weekStart)}，${week.count} 条`}
                  aria-pressed={selected}
                  onClick={() => onSelect(week.weekStart)}
                  className="mt-4 grid h-10 w-9 place-items-end justify-center rounded-lg bg-transparent transition-[transform,opacity] active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  <span
                    className={`w-5 rounded-md transition-[box-shadow,opacity] ${
                      selected
                        ? 'opacity-100 shadow-[0_0_0_2px_var(--color-brand)]'
                        : 'opacity-85 hover:opacity-100'
                    }`}
                    style={{
                      height,
                      background: fillFor(week.count),
                      minHeight: week.count > 0 ? 8 : 4,
                    }}
                  />
                </button>
              </div>
            )
          })}
        </div>
      </div>
      {chronological.length > 12 && (
        <p className="pt-1 text-center text-[11px] text-muted">左右滑动查看更早的周 · 也可用下方箭头切换</p>
      )}
    </div>
  )
}
