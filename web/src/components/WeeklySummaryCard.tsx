import {useCallback, useEffect, useState} from 'react'
import {FileText, RefreshCw, WandSparkles} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import {Link} from 'wouter'
import {generateWeeklySummary, getWeeklySummary, type WeeklySummary} from '../lib/api'

// ReactMarkdown escapes raw HTML by default; keep the same prose treatment as
// the existing summary notes without importing the whole workspace page here.
const MARKDOWN_PROSE = 'prose prose-sm max-w-none break-words text-ink dark:prose-invert prose-headings:tracking-[-0.012em] prose-a:text-brand [&_pre]:overflow-x-auto [&_table]:block [&_table]:overflow-x-auto [&_code]:break-all'

function formatWeek(weekStart: string) {
  const [year, month, day] = weekStart.split('-').map(Number)
  const start = new Date(year, month - 1, day)
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  return `${start.getMonth() + 1}月${start.getDate()}日—${end.getMonth() + 1}月${end.getDate()}日`
}

/**
 * A summary is fetched only while this card is mounted. History mounts it solely
 * for expanded week groups, so opening one week never fetches every archive.
 */
export function WeeklySummaryCard({weekStart, compact = false, onReferenceNavigate}: {weekStart: string; compact?: boolean; onReferenceNavigate?: (jobId: string) => void}) {
  const [summary, setSummary] = useState<WeeklySummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [failed, setFailed] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setFailed(false)
    try {
      setSummary(await getWeeklySummary(weekStart))
    } catch {
      setSummary(null)
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [weekStart])

  useEffect(() => { void load() }, [load])
  useEffect(() => { setExpanded(false) }, [weekStart])
  useEffect(() => {
    if (summary?.status !== 'GENERATING') return
    const timer = window.setTimeout(() => void load(), 1200)
    return () => window.clearTimeout(timer)
  }, [load, summary?.status])

  const generate = async () => {
    setGenerating(true)
    setFailed(false)
    try {
      setSummary(await generateWeeklySummary(weekStart, summary?.status === 'STALE' || summary?.status === 'COMPLETED'))
    } catch {
      setFailed(true)
    } finally {
      setGenerating(false)
    }
  }

  const status = summary?.status
  const stale = status === 'STALE'
  const hasContent = status === 'COMPLETED' && Boolean(summary?.content)
  const message = failed || status === 'FAILED'
    ? (summary?.error || '周总结暂不可用，请稍后重试。')
    : status === 'EMPTY'
      ? '本周还没有可总结的内容。'
      : status === 'GENERATING'
        ? '本周总结正在生成。'
        : stale
          ? '本周内容已变化，请更新总结。'
          : '本周尚未生成总结。'
  const actionLabel = stale ? '更新总结' : status === 'COMPLETED' ? '重新生成' : '生成本周总结'

  return <section className={compact ? 'border-b border-line/60 py-3' : 'rounded-3xl bg-panel p-4 shadow-card'}>
    <div className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2"><FileText size={compact ? 14 : 16} className="shrink-0 text-brand" /><div><h2 className={compact ? 'text-sm font-semibold text-ink' : 'text-base font-semibold text-ink'}>本周总结</h2><p className="mt-0.5 text-xs text-muted">{formatWeek(weekStart)}</p></div></div>
      {status === 'COMPLETED' && <span className="shrink-0 rounded-full bg-brandSoft px-2.5 py-1 text-xs text-brand">已生成</span>}
      {stale && <span className="shrink-0 rounded-full bg-warning/15 px-2.5 py-1 text-xs text-warning">待更新</span>}
    </div>
    {loading ? <div className="mt-3 h-10 animate-pulse rounded-xl bg-lift" /> : hasContent ? <>
      <div className={`mt-3 text-sm ${MARKDOWN_PROSE} ${compact && !expanded ? 'line-clamp-4' : ''}`}><ReactMarkdown components={{
        // Model-authored Markdown is display-only. Navigation is restricted to
        // the server-validated references rendered below.
        a: ({children}) => <span>{children}</span>,
        img: ({alt}) => <span>{alt ?? ''}</span>,
      }}>{summary?.content ?? ''}</ReactMarkdown></div>
      {compact && <button type="button" onClick={() => setExpanded((value) => !value)} className="mt-2 text-xs text-brand hover:underline">{expanded ? '收起' : '展开全文'}</button>}
      {(!compact || expanded) && summary?.references.length ? <div className="mt-3 grid gap-1.5 border-t border-line pt-3 text-sm">
        {summary.references.map((reference) => <Link key={reference.job_id} href={`/jobs/${reference.job_id}`} onClick={() => onReferenceNavigate?.(reference.job_id)} className="truncate text-brand hover:underline">↗ {reference.title}</Link>)}
      </div> : null}
      <button type="button" onClick={() => void generate()} disabled={generating} className="mt-3 inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-lift px-3 text-xs text-muted hover:bg-line/70 disabled:opacity-50"><RefreshCw size={13} className={generating ? 'animate-spin' : undefined} />重新生成</button>
    </> : <div className="mt-3 grid gap-2">
      <p className="text-sm text-muted">{message}</p>
      {status !== 'EMPTY' && <button type="button" onClick={() => void generate()} disabled={generating || status === 'GENERATING'} className="inline-flex min-h-9 w-fit items-center gap-1.5 rounded-xl bg-brand px-3 text-xs font-medium text-white disabled:opacity-50"><WandSparkles size={14} />{generating ? '正在生成…' : actionLabel}</button>}
    </div>}
  </section>
}
