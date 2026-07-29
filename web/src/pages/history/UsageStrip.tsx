import {useCallback, useEffect, useState} from 'react'
import {ChevronDown, RefreshCw} from 'lucide-react'
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
  const [open, setOpen] = useState(false)

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
        <p className="text-sm text-muted">用量暂不可用</p>
      </div>
    )
  }
  if (!summary) return null

  const balance = summary.current_balance
  const balanceText = balance
    ? formatMoneyMicros(Math.round(balance.balance * 1_000_000), balance.currency)
    : '暂不可用'
  const tokenCells = [
    {label: '总 tokens', value: formatTokens(summary.tokens.all_recorded_total_tokens)},
    {label: '输入', value: formatTokens(summary.tokens.all_recorded_input_tokens)},
    {label: '输出', value: formatTokens(summary.tokens.all_recorded_output_tokens)},
  ]

  return (
    <div className="rounded-2xl bg-lift/45">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-11 w-full items-center gap-3 px-4 py-2.5 text-left transition-[background-color] hover:bg-line/30"
      >
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted sm:text-sm">{balanceScopeLabel(balance?.scope)}</p>
          <p className="mt-0.5 truncate text-base font-semibold tracking-[-0.015em] text-ink sm:text-lg">
            {balanceText}
            <span className="ml-2 font-normal text-muted">
              · {formatTokens(summary.tokens.all_recorded_total_tokens)} tokens
            </span>
          </p>
        </div>
        <ChevronDown
          size={16}
          className={`shrink-0 text-muted transition-transform ${open ? '' : '-rotate-90'}`}
        />
      </button>
      {open && (
        <div className="border-t border-line/60 px-4 pb-3.5 pt-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-muted">{balanceScopeLabel(balance?.scope)}</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.02em] text-ink sm:text-3xl">
                {balanceText}
              </p>
            </div>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                void load(true)
              }}
              disabled={refreshing}
              aria-label="刷新余额"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-lift text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-50"
            >
              <RefreshCw size={16} className={refreshing ? 'animate-spin' : undefined} />
            </button>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 border-t border-line/60 pt-3">
            {tokenCells.map((cell) => (
              <div key={cell.label} className="min-w-0">
                <p className="text-xs text-muted sm:text-sm">{cell.label}</p>
                <p className="mt-0.5 truncate text-base font-medium text-ink sm:text-lg">{cell.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
