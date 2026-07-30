import {useEffect, useRef} from 'react'
import type {WeeklySummary} from '../lib/api'
import {preferredScrollBehavior} from '../lib/scroll'

type WeeklySummaryStatus = WeeklySummary['status']

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

function weekStartKey(weekStart: number): string {
  const date = new Date(weekStart)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function statusLabel(status: WeeklySummaryStatus | undefined): string {
  switch (status) {
    case 'COMPLETED':
      return '已总结'
    case 'STALE':
      return '待更新'
    case 'GENERATING':
      return '生成中'
    case 'FAILED':
      return '失败'
    case 'EMPTY':
      return '无可总结'
    default:
      return '未总结'
  }
}

/** 柱底状态点：有结论才着色，未总结保持空心以免干扰柱高语义。 */
function StatusDot({status}: {status: WeeklySummaryStatus | undefined}) {
  if (!status || status === 'MISSING' || status === 'EMPTY') {
    return (
      <span
        className="mt-1 h-1.5 w-1.5 rounded-full border border-line/80 bg-transparent"
        aria-hidden
      />
    )
  }
  const tone =
    status === 'COMPLETED'
      ? 'bg-brand border-brand'
      : status === 'FAILED'
        ? 'bg-danger border-danger'
        : 'bg-warning border-warning'
  const pulse = status === 'GENERATING' ? 'animate-pulse' : ''
  return <span className={`mt-1 h-1.5 w-1.5 rounded-full border ${tone} ${pulse}`} aria-hidden />
}

export interface WeekNavigatorItem {
  weekStart: number
  count: number
}

export function WeekNavigator({
  weeks,
  selectedWeek,
  onSelect,
  summaryStatuses = {},
}: {
  weeks: WeekNavigatorItem[]
  selectedWeek: number | null
  onSelect: (weekStart: number) => void
  /** week_start (YYYY-MM-DD) → status；缺省视为未总结 */
  summaryStatuses?: Partial<Record<string, WeeklySummaryStatus>>
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
    scroller.scrollTo({left: Math.max(0, target), behavior: preferredScrollBehavior()})
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
          aria-label="按周浏览，柱底圆点表示周总结状态"
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
            const key = weekStartKey(week.weekStart)
            const status = summaryStatuses[key]
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
                  aria-label={`${weekRangeLabel(week.weekStart)}，${week.count} 条，${statusLabel(status)}`}
                  aria-pressed={selected}
                  title={`${weekRangeLabel(week.weekStart)} · ${week.count} 条 · ${statusLabel(status)}`}
                  onClick={() => onSelect(week.weekStart)}
                  className="mt-4 flex w-9 flex-col items-center rounded-lg bg-transparent transition-[transform,opacity] active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  <span
                    className="grid h-10 w-9 place-items-end justify-center"
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
                  </span>
                  <StatusDot status={status} />
                </button>
              </div>
            )
          })}
        </div>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-muted">
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden />
          已总结
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-warning" aria-hidden />
          待更新
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full border border-line/80" aria-hidden />
          未总结
        </span>
      </div>
      {chronological.length > 12 && (
        <p className="pt-1 text-center text-[11px] text-muted">左右滑动查看更早的周 · 也可用下方箭头切换</p>
      )}
    </div>
  )
}
