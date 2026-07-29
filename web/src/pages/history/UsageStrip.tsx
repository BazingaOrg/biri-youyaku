import {useCallback, useEffect, useState} from 'react'
import {RefreshCw} from 'lucide-react'
import {getCostSummary, type CostSummaryResponse} from '../../lib/api'

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
      <div className="rounded-2xl bg-lift/45 px-4 py-3">
        <p className="text-sm text-muted">余额暂不可用</p>
      </div>
    )
  }
  if (!summary) return null

  const balance = summary.current_balance

  return (
    <div className="flex items-center justify-between gap-3 rounded-2xl bg-lift/45 px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm text-muted">{balanceScopeLabel(balance?.scope)}</p>
        <p className="mt-0.5 text-xl font-semibold tracking-[-0.02em] text-ink sm:text-2xl">
          {balance
            ? formatMoneyMicros(Math.round(balance.balance * 1_000_000), balance.currency)
            : '暂不可用'}
        </p>
      </div>
      <button
        type="button"
        onClick={() => void load(true)}
        disabled={refreshing}
        aria-label="刷新余额"
        className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-lift text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-50"
      >
        <RefreshCw size={16} className={refreshing ? 'animate-spin' : undefined} />
      </button>
    </div>
  )
}
