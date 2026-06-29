import type {WeeklyStats} from '../lib/stats'

type WeekBar = WeeklyStats & {key: string}

export function WeekBars({weeks}: {weeks: WeekBar[]}) {
  const width = 520
  const height = 180
  const padding = {top: 16, right: 10, bottom: 28, left: 30}
  const plotWidth = width - padding.left - padding.right
  const plotHeight = height - padding.top - padding.bottom
  const maxCount = Math.max(1, ...weeks.map((week) => week.count))
  const barGap = 8
  const barWidth = Math.max(10, (plotWidth - barGap * (weeks.length - 1)) / weeks.length)

  return (
    <div className="overflow-x-auto pb-1">
      <svg
        role="img"
        aria-label="最近 12 周每周完成的总结数量"
        viewBox={`0 0 ${width} ${height}`}
        className="min-w-[420px] max-w-full"
      >
        <line
          x1={padding.left}
          x2={width - padding.right}
          y1={padding.top + plotHeight}
          y2={padding.top + plotHeight}
          stroke="var(--color-border)"
        />
        {weeks.map((week, index) => {
          const valueHeight = (week.count / maxCount) * plotHeight
          const x = padding.left + index * (barWidth + barGap)
          const y = padding.top + plotHeight - valueHeight
          return (
            <g key={week.key}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(valueHeight, week.count > 0 ? 3 : 0)}
                rx={5}
                fill="var(--color-brand)"
                opacity={week.count > 0 ? 0.85 : 0.16}
              >
                <title>{`${week.label}：${week.count} 个总结`}</title>
              </rect>
              <text
                x={x + barWidth / 2}
                y={height - 10}
                textAnchor="middle"
                className="fill-current text-[10px] text-muted"
              >
                {index % 2 === 0 || weeks.length <= 8 ? week.label : ''}
              </text>
              {week.count > 0 && (
                <text
                  x={x + barWidth / 2}
                  y={Math.max(10, y - 5)}
                  textAnchor="middle"
                  className="fill-current text-[10px] font-medium text-ink"
                >
                  {week.count}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
