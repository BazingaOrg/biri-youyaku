import {useCallback, useEffect, useRef, useState} from 'react'
import {FileText, RefreshCw, Trash2, WandSparkles} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import {Link} from 'wouter'
import {
  deleteWeeklySummary,
  generateWeeklySummary,
  getWeeklySummary,
  type WeeklySummary,
} from '../lib/api'
import {PROSE} from '../lib/prose'
import {ConfirmDialog} from './ConfirmDialog'

function formatWeek(weekStart: string) {
  const [year, month, day] = weekStart.split('-').map(Number)
  const start = new Date(year, month - 1, day)
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  return `${start.getMonth() + 1}月${start.getDate()}日—${end.getMonth() + 1}月${end.getDate()}日`
}

export type WeeklySummaryStatus = WeeklySummary['status']

/**
 * A summary is fetched only while this card is mounted. History mounts it solely
 * for the selected week, so opening one week never fetches every archive.
 *
 * onStatusChange is held in a ref so parent re-renders (inline callbacks) never
 * retrigger the fetch loop that caused history page jitter.
 */
export function WeeklySummaryCard({
  weekStart,
  compact = false,
  onReferenceNavigate,
  onStatusChange,
}: {
  weekStart: string
  compact?: boolean
  onReferenceNavigate?: (jobId: string) => void
  /** Notify parent (e.g. week bar dots) when status loads or changes. */
  onStatusChange?: (status: WeeklySummaryStatus | null) => void
}) {
  const [summary, setSummary] = useState<WeeklySummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [failed, setFailed] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const onStatusChangeRef = useRef(onStatusChange)
  const lastReportedStatusRef = useRef<WeeklySummaryStatus | null | undefined>(undefined)

  useEffect(() => {
    onStatusChangeRef.current = onStatusChange
  }, [onStatusChange])

  const reportStatus = useCallback((status: WeeklySummaryStatus | null) => {
    if (lastReportedStatusRef.current === status) return
    lastReportedStatusRef.current = status
    onStatusChangeRef.current?.(status)
  }, [])

  const load = useCallback(async (opts?: {silent?: boolean}) => {
    if (!opts?.silent) setLoading(true)
    setFailed(false)
    try {
      const next = await getWeeklySummary(weekStart)
      setSummary(next)
      reportStatus(next.status)
    } catch {
      setSummary(null)
      setFailed(true)
      reportStatus(null)
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [reportStatus, weekStart])

  // Only weekStart should reload the card — never parent callback identity.
  useEffect(() => {
    setExpanded(false)
    setConfirmDelete(false)
    lastReportedStatusRef.current = undefined
    void load()
  }, [load, weekStart])

  useEffect(() => {
    if (summary?.status !== 'GENERATING') return
    // Silent poll while generating so the skeleton does not flash.
    const timer = window.setTimeout(() => void load({silent: true}), 1200)
    return () => window.clearTimeout(timer)
  }, [load, summary?.status])

  const generate = async () => {
    setGenerating(true)
    setFailed(false)
    try {
      const next = await generateWeeklySummary(weekStart, summary?.status === 'STALE' || summary?.status === 'COMPLETED')
      setSummary(next)
      reportStatus(next.status)
    } catch {
      setFailed(true)
    } finally {
      setGenerating(false)
    }
  }

  const remove = async () => {
    setDeleting(true)
    setFailed(false)
    try {
      const next = await deleteWeeklySummary(weekStart)
      setSummary(next)
      reportStatus(next.status)
      setConfirmDelete(false)
      setExpanded(false)
    } catch {
      setFailed(true)
    } finally {
      setDeleting(false)
    }
  }

  const status = summary?.status
  const stale = status === 'STALE'
  const hasContent = status === 'COMPLETED' && Boolean(summary?.content)
  // Any persisted week record can be cleared; MISSING has nothing stored.
  const canDelete = Boolean(status && status !== 'MISSING' && status !== 'GENERATING')
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

  return (
    <>
      <section className={compact ? 'border-b border-line/60 py-3' : 'rounded-3xl bg-panel p-4 shadow-card'}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <FileText size={compact ? 14 : 16} className="shrink-0 text-brand" />
            <div>
              <h2 className={compact ? 'text-sm font-semibold text-ink' : 'text-base font-semibold text-ink'}>本周总结</h2>
              <p className="mt-0.5 text-xs text-muted">{formatWeek(weekStart)}</p>
            </div>
          </div>
          {/* compact 时状态上移到周切换标题，避免与 header pill 重复 */}
          {!compact && (
            <div className="flex shrink-0 items-center gap-2">
              {status === 'COMPLETED' && <span className="rounded-full bg-brandSoft px-2.5 py-1 text-xs text-brand">已总结</span>}
              {stale && <span className="rounded-full bg-warning/15 px-2.5 py-1 text-xs text-warning">待更新</span>}
            </div>
          )}
        </div>
        {loading ? (
          <div className="mt-3 h-10 animate-pulse rounded-xl bg-lift" />
        ) : hasContent ? (
          <>
            <div className={`mt-3 text-sm ${PROSE} ${compact && !expanded ? 'line-clamp-4' : ''}`}>
              <ReactMarkdown
                components={{
                  // Model-authored Markdown is display-only. Navigation is restricted to
                  // the server-validated references rendered below.
                  a: ({children}) => <span>{children}</span>,
                  img: ({alt}) => <span>{alt ?? ''}</span>,
                }}
              >
                {summary?.content ?? ''}
              </ReactMarkdown>
            </div>
            {compact && (
              <button type="button" onClick={() => setExpanded((value) => !value)} className="mt-2 text-xs text-brand hover:underline">
                {expanded ? '收起' : '展开全文'}
              </button>
            )}
            {(!compact || expanded) && summary?.references.length ? (
              <div className="mt-3 grid gap-1.5 border-t border-line pt-3 text-sm">
                {summary.references.map((reference) => (
                  <Link
                    key={reference.job_id}
                    href={`/jobs/${reference.job_id}`}
                    onClick={() => onReferenceNavigate?.(reference.job_id)}
                    className="truncate text-brand hover:underline"
                  >
                    ↗ {reference.title}
                  </Link>
                ))}
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void generate()}
                disabled={generating || deleting}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-lift px-3 text-xs text-muted hover:bg-line/70 disabled:opacity-50"
              >
                <RefreshCw size={13} className={generating ? 'animate-spin' : undefined} />
                重新生成
              </button>
              {canDelete && (
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  disabled={generating || deleting}
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-lift px-3 text-xs text-danger hover:bg-danger/10 disabled:opacity-50"
                >
                  <Trash2 size={13} />
                  删除总结
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="mt-3 grid gap-2">
            <p className="text-sm text-muted">{message}</p>
            <div className="flex flex-wrap items-center gap-2">
              {status !== 'EMPTY' && (
                <button
                  type="button"
                  onClick={() => void generate()}
                  disabled={generating || deleting || status === 'GENERATING'}
                  className="inline-flex min-h-9 w-fit items-center gap-1.5 rounded-xl bg-brand px-3 text-xs font-medium text-white disabled:opacity-50"
                >
                  <WandSparkles size={14} />
                  {generating ? '正在生成…' : actionLabel}
                </button>
              )}
              {canDelete && (
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  disabled={generating || deleting}
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-xl bg-lift px-3 text-xs text-danger hover:bg-danger/10 disabled:opacity-50"
                >
                  <Trash2 size={13} />
                  删除总结
                </button>
              )}
            </div>
          </div>
        )}
      </section>
      <ConfirmDialog
        open={confirmDelete}
        title="删除本周总结？"
        description="只删除这份周总结缓存，不会删除该周的视频任务记录。之后可重新生成。"
        confirmLabel="删除总结"
        danger
        loading={deleting}
        onConfirm={() => void remove()}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  )
}
