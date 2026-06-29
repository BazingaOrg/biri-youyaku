import {useCallback, useEffect, useMemo, useState} from 'react'
import type {ReactNode} from 'react'
import {ArrowLeft, BarChart3, Clock3, Coins, Hash, History, RotateCw, Sparkles} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {Heatmap} from '../components/Heatmap'
import {PageLoading} from '../components/Spinner'
import {WeekBars} from '../components/WeekBars'
import {getLlmBalance, listJobs, type Job, type LlmBalanceResponse} from '../lib/api'
import {formatDuration} from '../lib/format'
import {buildStats, type WeeklyStats} from '../lib/stats'

const PAGE_SIZE = 200

async function loadAllJobs(cancelled?: () => boolean): Promise<Job[]> {
  const jobs: Job[] = []
  let cursor: number | null | undefined = null
  do {
    const response: Awaited<ReturnType<typeof listJobs>> = await listJobs({limit: PAGE_SIZE, cursor})
    if (cancelled?.()) return []
    jobs.push(...response.jobs)
    cursor = response.next_cursor ?? null
  } while (cursor != null)
  return jobs
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(2)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return String(tokens)
}

function formatMoney(value: number, currency = 'CNY'): string {
  if (currency === 'USD') return `$${value.toFixed(2)}`
  return `¥${value.toFixed(2)}`
}

function deltaText(current: number, previous: number): string {
  if (previous === 0) return current > 0 ? '上周无记录' : '无变化'
  const delta = ((current - previous) / previous) * 100
  if (Math.abs(delta) < 1) return '基本持平'
  return `${delta > 0 ? '+' : ''}${delta.toFixed(0)}%`
}

function StatCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode
  label: string
  value: string
  detail?: string
}) {
  return (
    <div className="rounded-3xl bg-panel p-4 shadow-card">
      <div className="flex items-center gap-2 text-xs text-muted">
        <span className="grid h-7 w-7 place-items-center rounded-xl bg-brandSoft text-brand">{icon}</span>
        {label}
      </div>
      <p className="mt-3 font-serif text-3xl leading-none tracking-[-0.012em] text-ink">{value}</p>
      {detail && <p className="mt-2 text-xs text-muted">{detail}</p>}
    </div>
  )
}

function WeeklyCompare({current, previous}: {current: WeeklyStats; previous: WeeklyStats}) {
  return (
    <section className="grid gap-3 rounded-3xl bg-panel p-4 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">周对比</h2>
          <p className="mt-1 text-xs text-muted">本周与上周的总结量、tokens 和视频时长。</p>
        </div>
        <span className="rounded-full bg-brandSoft px-3 py-1 text-xs font-medium text-brand">
          {deltaText(current.count, previous.count)}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {[
          ['总结数', `${current.count}`, `${previous.count}`],
          ['tokens', formatTokens(current.tokens), formatTokens(previous.tokens)],
          ['估算花费', formatMoney(current.estimatedCostCny), formatMoney(previous.estimatedCostCny)],
          ['视频时长', formatDuration(current.durationSeconds), formatDuration(previous.durationSeconds)],
        ].map(([label, now, before]) => (
          <div key={label} className="rounded-2xl bg-lift/70 px-3 py-2">
            <p className="text-xs text-muted">{label}</p>
            <p className="mt-1 text-sm font-medium text-ink">
              {now}
              <span className="ml-2 text-xs font-normal text-muted">上周 {before}</span>
            </p>
          </div>
        ))}
      </div>
      {current.topTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-xs text-muted">本周关键词</span>
          {current.topTags.map((item) => (
            <span key={item.tag} className="rounded-full bg-brandSoft/60 px-2.5 py-1 text-xs text-brand">
              #{item.tag} {item.count}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

function BalanceCard() {
  const [balance, setBalance] = useState<LlmBalanceResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (refresh = false) => {
    setLoading(true)
    try {
      const response = await getLlmBalance(refresh)
      setBalance(response.supported ? response : null)
    } catch {
      setBalance(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(false)
  }, [load])

  if (!balance?.supported || balance.balance == null) return null

  return (
    <section className="grid gap-3 rounded-3xl bg-ink p-4 text-canvas shadow-card">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-canvas/70">API Key 余额</p>
          <p className="mt-1 truncate text-sm font-medium">{balance.provider}</p>
        </div>
        <button
          type="button"
          onClick={() => void load(true)}
          disabled={loading}
          aria-label="刷新余额"
          className="grid h-10 w-10 place-items-center rounded-2xl bg-canvas/10 text-canvas transition-[transform,background-color] hover:bg-canvas/16 active:scale-95 disabled:opacity-50"
        >
          <RotateCw size={16} className={loading ? 'animate-spin' : undefined} />
        </button>
      </div>
      <p className="font-serif text-4xl leading-none tracking-[-0.012em]">
        {formatMoney(balance.balance, balance.currency)}
      </p>
    </section>
  )
}

export function StatsPage() {
  const [, navigate] = useLocation()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async (cancelled?: () => boolean) => {
    setLoading(true)
    setError(false)
    try {
      const next = await loadAllJobs(cancelled)
      if (!cancelled?.()) setJobs(next)
    } catch {
      if (!cancelled?.()) {
        setJobs([])
        setError(true)
      }
    } finally {
      if (!cancelled?.()) setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void load(() => cancelled)
    return () => {
      cancelled = true
    }
  }, [load])

  const stats = useMemo(() => buildStats(jobs), [jobs])
  const handleBack = () => {
    if (window.history.length > 1) window.history.back()
    else navigate('/')
  }

  return (
    <div className="grid min-h-[calc(100dvh-3rem)] content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
      <header className="grid gap-4 px-4 sm:px-5">
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={handleBack}
            className="inline-flex min-h-10 w-fit items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
          >
            <ArrowLeft size={16} />
            返回
          </button>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/history"
              className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
            >
              <History size={16} />
              历史
            </Link>
            <Link
              href="/"
              className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-brand px-3 text-sm font-medium text-white shadow-card transition-[transform,filter] hover:brightness-105 active:scale-95"
            >
              <Sparkles size={16} />
              新建
            </Link>
          </div>
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">统计</h1>
          <p className="mt-1 text-sm text-muted">按周查看总结习惯、tokens 和视频时长。</p>
        </div>
      </header>

      <section className="grid gap-4 px-4 sm:px-5">
        {loading && <PageLoading label="加载统计…" />}

        {!loading && error && (
          <div className="grid justify-items-center gap-3 rounded-3xl bg-panel py-12 text-center shadow-card">
            <p className="text-sm text-muted">加载失败，请检查网络后重试</p>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
            >
              <RotateCw size={15} />
              重试
            </button>
          </div>
        )}

        {!loading && !error && (
          <>
            <BalanceCard />

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <StatCard
                icon={<BarChart3 size={15} />}
                label="已完成总结"
                value={String(stats.totals.completed)}
                detail={`本周 ${stats.thisWeek.count} 个`}
              />
              <StatCard
                icon={<Hash size={15} />}
                label="总 tokens"
                value={formatTokens(stats.totals.tokens)}
                detail={`估算 ${formatMoney(stats.totals.estimatedCostCny)}`}
              />
              <StatCard
                icon={<Clock3 size={15} />}
                label="视频总时长"
                value={formatDuration(stats.totals.durationSeconds)}
                detail="按已完成任务统计"
              />
              <StatCard
                icon={<Coins size={15} />}
                label="本周估算花费"
                value={formatMoney(stats.thisWeek.estimatedCostCny)}
                detail={`上周 ${formatMoney(stats.lastWeek.estimatedCostCny)}`}
              />
            </div>

            <section className="rounded-3xl bg-panel p-4 shadow-card">
              <div className="mb-3">
                <h2 className="text-base font-semibold text-ink">活跃热力图</h2>
                <p className="mt-1 text-xs text-muted">最近 26 周每天完成的总结数量。</p>
              </div>
              <Heatmap days={stats.heatmap} />
            </section>

            <WeeklyCompare current={stats.thisWeek} previous={stats.lastWeek} />

            <section className="rounded-3xl bg-panel p-4 shadow-card">
              <div className="mb-3">
                <h2 className="text-base font-semibold text-ink">最近 12 周</h2>
                <p className="mt-1 text-xs text-muted">每周完成的总结数。</p>
              </div>
              <WeekBars weeks={stats.byWeek} />
            </section>
          </>
        )}
      </section>
    </div>
  )
}
