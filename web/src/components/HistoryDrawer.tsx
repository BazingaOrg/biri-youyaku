import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import type {MouseEvent as ReactMouseEvent} from 'react'
import {Search, Trash, Trash2, X} from 'lucide-react'
import {deleteAllJobs, deleteJob, listJobs, type Job} from '../lib/api'
import {formatDate, formatDuration, formatStatus} from '../lib/format'
import {useToast} from './ToastProvider'

interface HistoryDrawerProps {
  open: boolean
  onClose: () => void
  onOpenJob: (jobId: string) => void
  onDeleted?: (jobId: string) => void
  /** 用于触发列表刷新（jobId 或状态变化时拉新数据）。 */
  refreshKey?: string | null
}

const RUNNING = new Set([
  'PENDING',
  'FETCHING_META',
  'DOWNLOADING_AUDIO',
  'TRANSCRIBING',
  'TRANSCRIPT_READY',
  'SUMMARIZING',
  'EMAILING',
])

const PAGE_SIZE = 30

export function HistoryDrawer({open, onClose, onOpenJob, onDeleted, refreshKey}: HistoryDrawerProps) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [cursor, setCursor] = useState<number | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [query, setQuery] = useState('')
  const [clearing, setClearing] = useState(false)
  const toast = useToast()
  const scrollRef = useRef<HTMLDivElement | null>(null)

  // 首次打开 / refreshKey 变化 → 重新拉第一页
  useEffect(() => {
    if (!open) return
    let canceled = false
    setLoading(true)
    setQuery('')
    listJobs({limit: PAGE_SIZE})
      .then((response) => {
        if (canceled) return
        setJobs(response.jobs)
        setCursor(response.next_cursor ?? null)
        setHasMore(Boolean(response.next_cursor))
      })
      .catch(() => {
        if (canceled) return
        setJobs([])
        setHasMore(false)
      })
      .finally(() => {
        if (!canceled) setLoading(false)
      })
    return () => {
      canceled = true
    }
  }, [open, refreshKey])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || cursor == null) return
    setLoadingMore(true)
    try {
      const response = await listJobs({limit: PAGE_SIZE, cursor})
      setJobs((current) => [...current, ...response.jobs])
      setCursor(response.next_cursor ?? null)
      setHasMore(Boolean(response.next_cursor))
    } catch {
      setHasMore(false)
    } finally {
      setLoadingMore(false)
    }
  }, [cursor, hasMore, loadingMore])

  // 滑到底自动加载下一页
  useEffect(() => {
    const el = scrollRef.current
    if (!el || !open) return
    const onScroll = () => {
      const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 80
      if (nearBottom) void loadMore()
    }
    el.addEventListener('scroll', onScroll, {passive: true})
    return () => el.removeEventListener('scroll', onScroll)
  }, [open, loadMore])

  // 客户端模糊搜索（标题 / UP / BVID 任一命中即可）
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return jobs
    return jobs.filter((job) => {
      const haystack = [
        job.title ?? '',
        job.author ?? '',
        job.bvid ?? '',
        job.url ?? '',
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(q)
    })
  }, [jobs, query])

  const handleOpen = (jobId: string) => {
    onClose()
    onOpenJob(jobId)
  }

  const handleDelete = async (jobId: string, event: ReactMouseEvent) => {
    event.stopPropagation()
    try {
      await deleteJob(jobId)
      setJobs((current) => current.filter((j) => j.id !== jobId))
      onDeleted?.(jobId)
    } catch {
      // 静默：下次开抽屉会刷新
    }
  }

  const handleClearCompleted = async () => {
    // 简单确认，避免误点。原生 confirm 在 mobile 也能 work。
    if (!window.confirm('删除所有已完成 / 已失败 / 已取消的任务？进行中任务不受影响。')) return
    setClearing(true)
    try {
      const response = await deleteAllJobs()
      const total = response.deleted_count + response.skipped_count
      const detail = response.skipped_count > 0
        ? `已删除 ${response.deleted_count} 个，跳过 ${response.skipped_count} 个进行中任务`
        : `已删除 ${response.deleted_count} 个`
      toast.success('已清理', detail)
      // 重新拉首页
      const fresh = await listJobs({limit: PAGE_SIZE})
      setJobs(fresh.jobs)
      setCursor(fresh.next_cursor ?? null)
      setHasMore(Boolean(fresh.next_cursor))
      void total // 让 ts 别报 unused
    } catch (err) {
      toast.error('清理失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setClearing(false)
    }
  }

  return (
    <div
      className={`fixed inset-0 z-40 transition-opacity duration-[320ms] ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
        open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
      }`}
      onClick={onClose}
      aria-hidden={!open}
    >
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" />
      <aside
        onClick={(e) => e.stopPropagation()}
        className={`absolute inset-x-0 bottom-0 mx-auto flex h-[70vh] w-full max-w-xl flex-col rounded-t-3xl border-t border-line bg-canvas shadow-card transition-transform duration-[320ms] ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
          open ? 'translate-y-0' : 'translate-y-full'
        }`}
      >
        <div className="pt-2">
          <div className="mx-auto h-1.5 w-12 rounded-full bg-line" />
        </div>
        <header className="flex items-center justify-between gap-3 px-5 py-3">
          <h2 className="text-base font-semibold">历史</h2>
          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="清空已完成"
              onClick={() => void handleClearCompleted()}
              disabled={clearing || jobs.length === 0}
              className="grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-lift hover:text-danger disabled:opacity-40"
              title="清空已完成 / 失败 / 取消的任务"
            >
              <Trash size={16} />
            </button>
            <button
              type="button"
              aria-label="关闭"
              onClick={onClose}
              className="grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* 搜索框 */}
        <div className="px-5 pb-2">
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
            />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜标题 / UP 主 / BVID"
              className="min-h-9 w-full rounded-xl bg-lift py-1 pl-9 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30"
            />
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 pb-4">
          {loading && <p className="py-6 text-center text-sm text-muted">加载中</p>}
          {!loading && jobs.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">还没有任务记录</p>
          )}
          {!loading && jobs.length > 0 && filtered.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">没有匹配「{query}」的记录</p>
          )}
          <ul className="grid gap-2">
            {filtered.map((job) => {
              const isRunning = RUNNING.has(job.status)
              return (
                <li key={job.id}>
                  <button
                    type="button"
                    onClick={() => handleOpen(job.id)}
                    className="group grid w-full grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-2xl border border-line bg-panel p-3 text-left transition hover:border-brand/30 hover:bg-brandSoft/30 active:scale-[0.99]"
                  >
                    <div className="min-w-0">
                      <p className="line-clamp-2 break-words text-sm font-medium text-ink">
                        {job.title || job.url}
                      </p>
                      <p className="mt-1 truncate text-xs text-muted">
                        {job.author || '未知 UP'} · {formatDuration(job.duration)}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        <span
                          className={`rounded-full px-2 py-0.5 ${
                            job.status === 'COMPLETED'
                              ? 'bg-brandSoft text-brand'
                              : job.status === 'FAILED'
                                ? 'bg-danger/15 text-danger'
                                : isRunning
                                  ? 'bg-warning/15 text-warning'
                                  : 'bg-lift text-muted'
                          }`}
                        >
                          {formatStatus(job.status)}
                        </span>
                        <span className="text-muted">{formatDate(job.created_at)}</span>
                      </p>
                    </div>
                    <span
                      role="button"
                      aria-label="删除"
                      onClick={(e) => void handleDelete(job.id, e)}
                      className="grid h-9 w-9 shrink-0 self-start place-items-center rounded-xl text-muted opacity-100 transition hover:bg-lift hover:text-danger active:scale-95 sm:opacity-0 sm:group-hover:opacity-100"
                    >
                      <Trash2 size={15} />
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
          {loadingMore && (
            <p className="py-3 text-center text-xs text-muted">加载更多…</p>
          )}
          {!loadingMore && hasMore && !query && (
            <button
              type="button"
              onClick={() => void loadMore()}
              className="mt-2 w-full rounded-xl bg-lift py-2 text-xs text-muted transition hover:text-ink"
            >
              加载更多
            </button>
          )}
        </div>
      </aside>
    </div>
  )
}
