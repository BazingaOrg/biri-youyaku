import type {Job} from './api'

const DAY_MS = 24 * 60 * 60 * 1000
const WEEK_MS = 7 * DAY_MS
const HEATMAP_WEEKS = 26
const ESTIMATED_CNY_PER_MILLION_TOKENS = 2

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
  estimatedCostCny: number
  topTags: Array<{tag: string; count: number}>
}

export interface StatsSummary {
  heatmap: HeatmapDay[]
  thisWeek: WeeklyStats
  lastWeek: WeeklyStats
  byWeek: Array<WeeklyStats & {key: string}>
  totals: {
    completed: number
    tokens: number
    durationSeconds: number
    estimatedCostCny: number
  }
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function startOfWeek(date: Date): Date {
  const day = date.getDay()
  const mondayOffset = day === 0 ? -6 : 1 - day
  const base = startOfDay(date)
  base.setDate(base.getDate() + mondayOffset)
  return base
}

function dateKey(ts: number): string {
  const date = startOfDay(new Date(ts))
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function weekKey(ts: number): string {
  return dateKey(startOfWeek(new Date(ts)).getTime())
}

function totalTokens(job: Job): number {
  const usage = job.token_usage ?? {}
  const total = Number(usage.total_tokens)
  if (Number.isFinite(total) && total > 0) return total
  const input = Number(usage.input_tokens) || Number(usage.prompt_tokens) || 0
  const output = Number(usage.output_tokens) || Number(usage.completion_tokens) || 0
  return input + output
}

export function estimateCostCny(tokens: number): number {
  return (tokens / 1_000_000) * ESTIMATED_CNY_PER_MILLION_TOKENS
}

function summarizeWeek(label: string, startTs: number, jobs: Job[]): WeeklyStats {
  const endTs = startTs + WEEK_MS
  const tagCounts = new Map<string, number>()
  let tokens = 0
  let durationSeconds = 0
  let count = 0

  for (const job of jobs) {
    const ts = job.completed_at ?? job.updated_at
    if (job.status !== 'COMPLETED' || ts < startTs || ts >= endTs) continue
    count += 1
    tokens += totalTokens(job)
    durationSeconds += Number(job.duration) || 0
    for (const tag of job.tags ?? []) {
      if (tag) tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1)
    }
  }

  return {
    label,
    startTs,
    endTs,
    count,
    tokens,
    durationSeconds,
    estimatedCostCny: estimateCostCny(tokens),
    topTags: [...tagCounts.entries()]
      .map(([tag, tagCount]) => ({tag, count: tagCount}))
      .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
      .slice(0, 5),
  }
}

export function buildStats(jobs: Job[], now = new Date()): StatsSummary {
  const completed = jobs.filter((job) => job.status === 'COMPLETED')
  const today = startOfDay(now)
  const thisWeekStart = startOfWeek(now).getTime()
  const heatmapStart = new Date(thisWeekStart)
  heatmapStart.setDate(heatmapStart.getDate() - (HEATMAP_WEEKS - 1) * 7)

  const countsByDay = new Map<string, number>()
  let totalTokensValue = 0
  let totalDurationSeconds = 0

  for (const job of completed) {
    const ts = job.completed_at ?? job.updated_at
    countsByDay.set(dateKey(ts), (countsByDay.get(dateKey(ts)) ?? 0) + 1)
    totalTokensValue += totalTokens(job)
    totalDurationSeconds += Number(job.duration) || 0
  }

  const heatmap: HeatmapDay[] = []
  for (let i = 0; i < HEATMAP_WEEKS * 7; i += 1) {
    const date = new Date(heatmapStart)
    date.setDate(heatmapStart.getDate() + i)
    const key = dateKey(date.getTime())
    heatmap.push({date: key, ts: date.getTime(), count: countsByDay.get(key) ?? 0})
  }

  const thisWeek = summarizeWeek('本周', thisWeekStart, jobs)
  const lastWeek = summarizeWeek('上周', thisWeekStart - WEEK_MS, jobs)

  const byWeek: Array<WeeklyStats & {key: string}> = []
  for (let i = 11; i >= 0; i -= 1) {
    const startTs = thisWeekStart - i * WEEK_MS
    const start = new Date(startTs)
    byWeek.push({
      ...summarizeWeek(`${start.getMonth() + 1}/${start.getDate()}`, startTs, jobs),
      key: weekKey(startTs),
    })
  }

  return {
    heatmap,
    thisWeek,
    lastWeek,
    byWeek,
    totals: {
      completed: completed.length,
      tokens: totalTokensValue,
      durationSeconds: totalDurationSeconds,
      estimatedCostCny: estimateCostCny(totalTokensValue),
    },
  }
}
