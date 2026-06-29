import type {HeatmapDay} from '../lib/stats'

const CELL = 11
const GAP = 3
const LEFT = 24
const TOP = 20
const WEEK_COUNT = 26
const HEIGHT = TOP + 7 * (CELL + GAP)

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

function monthLabel(date: string): string {
  const [, month] = date.split('-')
  return `${Number(month)}月`
}

export function Heatmap({days}: {days: HeatmapDay[]}) {
  const width = LEFT + WEEK_COUNT * (CELL + GAP)
  const monthLabels = days.reduce<Array<{label: string; x: number}>>((labels, day, index) => {
    const previous = index > 0 ? days[index - 1] : null
    const currentMonth = day.date.slice(0, 7)
    if (index === 0 || previous?.date.slice(0, 7) !== currentMonth) {
      labels.push({label: monthLabel(day.date), x: LEFT + Math.floor(index / 7) * (CELL + GAP)})
    }
    return labels
  }, [])

  return (
    <div className="overflow-x-auto pb-1">
      <svg
        role="img"
        aria-label="最近 26 周每天完成的总结数量"
        viewBox={`0 0 ${width} ${HEIGHT}`}
        className="min-w-[390px] max-w-full text-muted"
      >
        {monthLabels.map((item) => (
          <text key={`${item.label}-${item.x}`} x={item.x} y={10} className="fill-current text-[10px]">
            {item.label}
          </text>
        ))}
        {['一', '三', '五'].map((label, index) => (
          <text key={label} x={0} y={TOP + (index * 2 + 1) * (CELL + GAP) + 8} className="fill-current text-[10px]">
            {label}
          </text>
        ))}
        {days.map((day, index) => {
          const week = Math.floor(index / 7)
          const weekday = index % 7
          return (
            <rect
              key={day.date}
              x={LEFT + week * (CELL + GAP)}
              y={TOP + weekday * (CELL + GAP)}
              width={CELL}
              height={CELL}
              rx={3}
              fill={fillFor(day.count)}
            >
              <title>{`${day.date}：${day.count} 个总结`}</title>
            </rect>
          )
        })}
      </svg>
    </div>
  )
}
