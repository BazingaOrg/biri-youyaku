import {useCallback, useEffect, useMemo, useState} from 'react'
import {ArrowLeft, Coins, History, RefreshCw, Sparkles} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {
  getCostSummary,
  type CostAmount,
  type CostSummaryResponse,
} from '../lib/api'
import {buildCostWeeks, costForWeek, localCurrentWeekStart} from '../lib/stats'
import {Skeleton} from '../components/Skeleton'
import {WeeklySummaryCard} from '../components/WeeklySummaryCard'

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(2)}M`
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`
  return String(tokens)
}

function formatMoneyMicros(micros: number, currency: string): string {
  const amount = micros / 1_000_000
  const prefix = currency === 'USD' ? '$' : currency === 'CNY' ? '¥' : `${currency} `
  const fraction = amount !== 0 && Math.abs(amount) < 0.01 ? 6 : 2
  return `${prefix}${amount.toFixed(fraction)}`
}

function formatAmounts(amounts: Iterable<CostAmount>): string {
  const values = [...amounts]
  return values.length ? values.map(({currency, micros}) => formatMoneyMicros(micros, currency)).join(' · ') : '暂不可用'
}

function formatTime(timestamp?: number): string {
  if (!timestamp) return '暂无更新时间'
  return new Intl.DateTimeFormat('zh-CN', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'}).format(timestamp)
}

function balanceScopeLabel(scope?: string): string {
  if (scope === 'key_limit') return 'API Key 可用限额'
  if (scope === 'account_credits') return '账户余额'
  return 'API 余额'
}

function CostTrend({summary}: {summary: CostSummaryResponse}) {
  const weeks = useMemo(() => buildCostWeeks(summary.weekly, summary.current_week_start), [summary.weekly, summary.current_week_start])
  const currencies = useMemo(() => [...new Set(summary.weekly.map((row) => row.currency).filter(Boolean))], [summary.weekly])
  if (!currencies.length) return <p className="text-xs text-muted">尚无供应商确认的费用数据。</p>

  return (
    <div className="grid gap-4">
      {currencies.map((currency) => <CurrencyTrend key={currency} currency={currency} weeks={weeks} />)}
    </div>
  )
}

function CurrencyTrend({currency, weeks}: {currency: string; weeks: ReturnType<typeof buildCostWeeks>}) {
  const values = weeks.map((week) => (week.amounts.get(currency) ?? 0) / 1_000_000)
  const max = Math.max(1e-9, ...values)
  const width = 360
  const height = 100
  const baseY = 76
  const points = values.map((value, index) => `${12 + (index * 336) / 11},${baseY - (value / max) * 54}`).join(' ')
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
        <span className="font-medium text-ink">{currency}</span>
        <span className="text-muted">最高 {formatMoneyMicros(Math.round(max * 1_000_000), currency)}</span>
      </div>
      <svg role="img" aria-label={`最近 12 周 ${currency} 真实费用`} viewBox={`0 0 ${width} ${height}`} className="block h-auto w-full">
        <line x1="12" x2="348" y1={baseY} y2={baseY} stroke="var(--color-border)" />
        <polyline points={points} fill="none" stroke="var(--color-brand)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {values.map((value, index) => {
          const x = 12 + (index * 336) / 11
          const y = baseY - (value / max) * 54
          return <g key={weeks[index].key}><circle cx={x} cy={y} r="2.5" fill="var(--color-brand)"><title>{`${weeks[index].label}：${formatMoneyMicros(Math.round(value * 1_000_000), currency)}`}</title></circle>{(index === 0 || index === 11 || index % 3 === 0) && <text x={x} y="94" textAnchor="middle" className="fill-current text-[8px] text-muted">{weeks[index].label}</text>}</g>
        })}
      </svg>
    </div>
  )
}

export function StatsPage() {
  const [, navigate] = useLocation()
  const [summary, setSummary] = useState<CostSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const fallbackWeekStart = useMemo(() => localCurrentWeekStart(), [])

  const load = useCallback(async (refreshBalance = false) => {
    if (refreshBalance) setRefreshing(true)
    else setLoading(true)
    setError(false)
    try { setSummary(await getCostSummary(refreshBalance)) } catch { setError(true) } finally { setLoading(false); setRefreshing(false) }
  }, [])
  useEffect(() => { void load() }, [load])
  const handleBack = () => window.history.length > 1 ? window.history.back() : navigate('/')
  const balanceSnapshot = summary?.current_balance ? summary.balances.find((item) => item.provider === summary.current_balance?.provider && item.scope === summary.current_balance?.scope) : undefined
  const weekStart = summary?.current_week_start ?? fallbackWeekStart
  const thisWeekCosts = summary ? costForWeek(summary.weekly, weekStart) : new Map<string, number>()
  const thisWeekAmounts = [...thisWeekCosts].map(([currency, micros]) => ({currency, micros}))
  const totalRequests = summary ? summary.tokens.confirmed_requests + summary.tokens.pending_requests + summary.tokens.unsupported_requests : 0

  return <div className="grid min-h-[calc(100dvh-3rem)] content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
    <header className="grid gap-4 px-4 sm:px-5">
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button type="button" onClick={handleBack} className="inline-flex min-h-10 w-fit items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted hover:bg-line/70 hover:text-ink active:scale-95"><ArrowLeft size={16} />返回</button>
        <div className="flex flex-wrap gap-2"><Link href="/history" className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted hover:bg-line/70 hover:text-ink active:scale-95"><History size={16} />历史</Link><Link href="/" className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-brand px-3 text-sm font-medium text-white shadow-card hover:brightness-105 active:scale-95"><Sparkles size={16} />新建</Link></div>
      </div>
      <div><h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">统计</h1><p className="mt-1 text-sm text-muted">查看 API 余额、已确认费用和本周内容总结。</p></div>
    </header>
    <section className="grid gap-4 px-4 sm:px-5">
      {loading && <Skeleton count={2} />}
      {!loading && error && <div className="grid justify-items-center gap-3 rounded-3xl bg-panel py-12 text-center shadow-card"><p className="text-sm text-muted">加载失败，请检查网络后重试</p><button type="button" onClick={() => void load()} className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted hover:bg-line/70 hover:text-ink"><RefreshCw size={15} />重试</button></div>}
      {!loading && !error && summary && <>
        <section className="grid gap-4 rounded-3xl bg-panel p-4 shadow-card">
          <div className="flex items-start justify-between gap-4"><div><p className="text-xs text-muted">{balanceScopeLabel(summary.current_balance?.scope)}</p>{summary.current_balance ? <><p className="mt-1 text-2xl font-semibold text-ink">{formatMoneyMicros(Math.round(summary.current_balance.balance * 1_000_000), summary.current_balance.currency)}</p><p className="mt-1 text-xs text-muted">{summary.current_balance.provider} · 更新于 {formatTime(balanceSnapshot?.observed_at)}</p></> : <p className="mt-1 text-sm text-muted">暂不可用</p>}</div><button type="button" onClick={() => void load(true)} disabled={refreshing} aria-label="刷新余额与费用" className="grid h-10 w-10 place-items-center rounded-2xl bg-lift text-muted hover:bg-line/70 hover:text-ink disabled:opacity-50"><RefreshCw size={16} className={refreshing ? 'animate-spin' : undefined} /></button></div>
          <div className="grid gap-3 border-t border-line pt-4 sm:grid-cols-2"><div><p className="text-xs text-muted">本周已确认消费</p><p className="mt-1 text-lg font-semibold text-ink">{formatAmounts(thisWeekAmounts)}</p></div><div><p className="text-xs text-muted">追踪开始以来已确认</p><p className="mt-1 text-lg font-semibold text-ink">{formatAmounts(summary.confirmed_costs)}</p></div></div>
          <p className="text-xs text-muted">费用覆盖：已确认 {summary.tokens.confirmed_requests} 次 · 待确认 {summary.tokens.pending_requests} 次 · 不支持 {summary.tokens.unsupported_requests} 次{totalRequests ? `（共 ${totalRequests} 次）` : ''}</p>
          <p className="text-xs text-muted">已确认费用从 {formatTime(summary.tracking_started_at ?? undefined)} 起按供应商响应记录，不等同于账户完整账单。</p>
          <div className="grid grid-cols-3 gap-2 border-t border-line pt-4 text-center"><div><p className="text-xs text-muted">总 tokens</p><p className="mt-1 text-sm font-medium text-ink">{formatTokens(summary.tokens.all_recorded_total_tokens)}</p></div><div><p className="text-xs text-muted">输入</p><p className="mt-1 text-sm font-medium text-ink">{formatTokens(summary.tokens.all_recorded_input_tokens)}</p></div><div><p className="text-xs text-muted">输出</p><p className="mt-1 text-sm font-medium text-ink">{formatTokens(summary.tokens.all_recorded_output_tokens)}</p></div></div>
          <div className="border-t border-line pt-4"><div className="mb-3 flex items-center gap-2"><Coins size={15} className="text-brand" /><div><h2 className="text-sm font-semibold text-ink">近 12 周已确认费用</h2><p className="mt-0.5 text-xs text-muted">仅统计供应商确认响应；不同币种分开展示，并非账户完整账单。</p></div></div><CostTrend summary={summary} /></div>
          {summary.by_operation.length > 0 && <div className="border-t border-line pt-4"><h2 className="text-sm font-semibold text-ink">按操作类型</h2><div className="mt-2 grid gap-2">{summary.by_operation.map((item) => <div key={`${item.operation}-${item.currency}`} className="flex items-center justify-between gap-3 rounded-2xl bg-lift px-3 py-2 text-sm"><span className="truncate text-muted">{item.operation} · {item.requests} 次</span><span className="shrink-0 font-medium text-ink">{formatMoneyMicros(item.micros, item.currency)}</span></div>)}</div></div>}
        </section>
        <WeeklySummaryCard weekStart={weekStart} />
      </>}
    </section>
  </div>
}
