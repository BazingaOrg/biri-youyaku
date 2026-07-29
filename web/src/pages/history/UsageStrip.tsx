import {useCallback, useEffect, useState} from 'react'
import {RefreshCw} from 'lucide-react'
import {getCostSummary, type CostSummaryResponse} from '../../lib/api'

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

function balanceScopeLabel(scope?: string): string {
  if (scope === 'key_limit') return 'API Key 可用限额'
  if (scope === 'account_credits') return '账户余额'
  return 'API 余额'
}

export function UsageStrip() {
  const [summary, setSummary] = useState<CostSummaryResponse | null>(null)
  const [error, setError] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async (refreshBalance = false) => {
    if (refreshBalance) setRefreshing(true)
    try {
      setSummary(await getCostSummary(refreshBalance))
      setError(false)
    } catch {
      setError(true)
    } finally {
      setRefreshing(false)
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (!loaded) return null
  if (error && !summary) {
    return (
      <div className="rounded-2xl bg-lift/45 px-3 py-2.5">
        <p className="text-xs text-muted">用量暂不可用</p>
      </div>
    )
  }
  if (!summary) return null

  const balance = summary.current_balance

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl bg-lift/45 px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <div className="min-w-0">
            <p className="text-[11px] text-muted">{balanceScopeLabel(balance?.scope)}</p>
            <p className="text-sm font-medium text-ink">
              {balance
                ? formatMoneyMicros(Math.round(balance.balance * 1_000_000), balance.currency)
                : '暂不可用'}
            </p>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
            <span>
              总 tokens <span className="font-medium text-ink">{formatTokens(summary.tokens.all_recorded_total_tokens)}</span>
            </span>
            <span>
              输入 <span className="font-medium text-ink">{formatTokens(summary.tokens.all_recorded_input_tokens)}</span>
            </span>
            <span>
              输出 <span className="font-medium text-ink">{formatTokens(summary.tokens.all_recorded_output_tokens)}</span>
            </span>
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={() => void load(true)}
        disabled={refreshing}
        aria-label="刷新余额"
        className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-lift text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-50"
      >
        <RefreshCw size={14} className={refreshing ? 'animate-spin' : undefined} />
      </button>
    </div>
  )
}
