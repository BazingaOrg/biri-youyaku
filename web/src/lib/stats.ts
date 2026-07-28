import type {WeeklyCost} from './api'

// 旧图表组件仍由应用编译，但统计页已不再使用完成量或估算费用。
export interface HeatmapDay {
  date: string
  count: number
  ts: number
}

export interface WeeklyStats {
  label: string
  startTs: number
  endTs: number
  count: number
  tokens: number
  durationSeconds: number
  topTags: Array<{tag: string; count: number}>
}

export interface CostWeek {
  key: string
  label: string
  amounts: Map<string, number>
}

function isoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function localCurrentWeekStart(timestamp = Date.now()): string {
  const date = new Date(timestamp)
  date.setHours(0, 0, 0, 0)
  const day = date.getDay()
  date.setDate(date.getDate() + (day === 0 ? -6 : 1 - day))
  return isoDate(date)
}

function weekDate(weekStart: string): Date {
  const [year, month, day] = weekStart.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function weekLabel(weekStart: string): string {
  const date = weekDate(weekStart)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function shiftWeeks(weekStart: string, weeks: number): string {
  const date = weekDate(weekStart)
  date.setDate(date.getDate() + weeks * 7)
  return isoDate(date)
}

/** 补齐 12 个自然周；每种货币独立绘制，绝不做汇率换算或混加。 */
export function buildCostWeeks(rows: WeeklyCost[], current = localCurrentWeekStart()): CostWeek[] {
  const weeks = Array.from({length: 12}, (_, index) => {
    const key = shiftWeeks(current, index - 11)
    return {key, label: weekLabel(key), amounts: new Map<string, number>()}
  })
  const byKey = new Map(weeks.map((week) => [week.key, week]))
  for (const row of rows) {
    const week = byKey.get(row.week_start)
    if (!week || !row.currency) continue
    week.amounts.set(row.currency, (week.amounts.get(row.currency) ?? 0) + Number(row.micros || 0))
  }
  return weeks
}

export function costForWeek(rows: WeeklyCost[], weekStart = localCurrentWeekStart()): Map<string, number> {
  const result = new Map<string, number>()
  for (const row of rows) {
    if (row.week_start !== weekStart || !row.currency) continue
    result.set(row.currency, (result.get(row.currency) ?? 0) + Number(row.micros || 0))
  }
  return result
}
