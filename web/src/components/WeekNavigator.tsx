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

  let lastMonthKey = ''

  return (
    <div className="overflow-x-auto pb-1">
      <div className="flex min-w-min items-end gap-1.5 py-1" role="list" aria-label="按周浏览">
        {chronological.map((week) => {
          const date = new Date(week.weekStart)
          const monthKey = `${date.getFullYear()}-${date.getMonth()}`
          const showMonth = monthKey !== lastMonthKey
          if (showMonth) lastMonthKey = monthKey
          const selected = selectedWeek === week.weekStart
          const height = 12 + Math.round((week.count / maxCount) * 20)
          return (
            <div key={week.weekStart} className="relative flex w-8 shrink-0 flex-col items-center gap-1" role="listitem">
              {showMonth && (
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] text-muted">
                  {date.getMonth() + 1}月
                </span>
              )}
              <button
                type="button"
                aria-label={`${weekRangeLabel(week.weekStart)}，${week.count} 条`}
                aria-pressed={selected}
                onClick={() => onSelect(week.weekStart)}
                className={`mt-4 flex w-8 items-end justify-center rounded-xl border transition-[transform,box-shadow,border-color] active:scale-95 ${
                  selected
                    ? 'border-brand shadow-[0_0_0_2px_color-mix(in_srgb,var(--color-brand)_35%,transparent)]'
                    : 'border-transparent hover:border-line'
                }`}
                style={{height: 36}}
              >
                <span
                  className="w-5 rounded-md"
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
  )
}
