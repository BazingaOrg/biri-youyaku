import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {ArrowLeft, Plus, RotateCw, Search, Trash, Trash2} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {ApiError, deleteAllJobs, deleteJob, listJobs, type Job} from '../lib/api'
import {formatDate, formatDuration, formatStatus} from '../lib/format'
import {isRunning} from '../lib/jobStatus'
import {AuthorLink} from '../components/AuthorLink'
import {useToast} from '../components/ToastProvider'
import {ConfirmDialog} from '../components/ConfirmDialog'

const PAGE_SIZE = 200
// 增量渲染：首屏只渲染 INITIAL 行，滚到底再补 STEP 行。零依赖地把 DOM 节点数压住，
// 上千条记录也不会一次性铺满 DOM 拖垮滚动。
const INITIAL_VISIBLE = 60
const VISIBLE_STEP = 40
// 删除撤销窗口（毫秒）：到点才真正提交后端删除。
const UNDO_WINDOW_MS = 5000

function IconTooltip({label, children, className = ''}: {label: string; children: ReactNode; className?: string}) {
  return (
    <span className={`group relative inline-flex ${className}`}>
      {children}
      <span className="pointer-events-none absolute left-1/2 top-full z-10 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-xs font-medium text-canvas opacity-0 shadow-card transition group-hover:opacity-100 group-focus-within:opacity-100">
        {label}
      </span>
    </span>
  )
}

function SkeletonRow() {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_2.75rem] items-start gap-2 rounded-2xl bg-lift/55 p-2">
      <div className="animate-pulse px-2 py-1.5">
        <div className="h-4 w-3/4 rounded bg-line/70" />
        <div className="mt-2 h-3 w-2/5 rounded bg-line/60" />
        <div className="mt-3 flex gap-2">
          <div className="h-4 w-14 rounded-full bg-line/60" />
          <div className="h-4 w-20 rounded bg-line/50" />
        </div>
      </div>
    </li>
  )
}

export function HistoryPage() {
  const [, navigate] = useLocation()
  const [jobs, setJobs] = useState<Job[]>([])
  // 初始即 true：避免首帧 jobs=[] && !loading 闪一下「还没有任务记录」空状态。
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [selectedAuthor, setSelectedAuthor] = useState<string | null>(null)
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE)
  const [confirmClearOpen, setConfirmClearOpen] = useState(false)
  const [clearing, setClearing] = useState(false)
  const toast = useToast()

  // 待提交的删除：id -> {timer, job}。撤销时清 timer 并恢复；到点 commitDelete 真正删后端。
  const pendingDeletes = useRef<Map<string, {timer: number; job: Job}>>(new Map())

  const loadFirstPage = useCallback(async (cancelled?: () => boolean) => {
    setLoading(true)
    setLoadError(false)
    try {
      const allJobs: Job[] = []
      let cursor: number | null | undefined = null
      do {
        const response: Awaited<ReturnType<typeof listJobs>> = await listJobs({limit: PAGE_SIZE, cursor})
        if (cancelled?.()) return
        allJobs.push(...response.jobs)
        cursor = response.next_cursor ?? null
      } while (cursor != null)
      if (cancelled?.()) return
      setJobs(allJobs)
    } catch {
      if (cancelled?.()) return
      setJobs([])
      setLoadError(true)
    } finally {
      if (!cancelled?.()) setLoading(false)
    }
  }, [])

  useEffect(() => {
    let canceled = false
    void loadFirstPage(() => canceled)
    return () => {
      canceled = true
    }
  }, [loadFirstPage])

  // 卸载时把还在撤销窗口里的删除立即提交，避免离开页面后丢删除。
  useEffect(() => {
    const pending = pendingDeletes.current
    return () => {
      for (const [jobId, entry] of pending) {
        window.clearTimeout(entry.timer)
        void deleteJob(jobId).catch(() => {})
      }
      pending.clear()
    }
  }, [])

  // 搜索防抖：输入态 query 即时回显，真正参与筛选的 debouncedQuery 延迟 200ms。
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 200)
    return () => window.clearTimeout(timer)
  }, [query])

  const authorStats = useMemo(() => {
    const counts = new Map<string, number>()
    for (const job of jobs) {
      const author = job.author?.trim() || '未知 UP'
      counts.set(author, (counts.get(author) ?? 0) + 1)
    }
    return [...counts.entries()]
      .map(([author, count]) => ({author, count}))
      .sort((a, b) => b.count - a.count || a.author.localeCompare(b.author))
  }, [jobs])

  useEffect(() => {
    if (!selectedAuthor) return
    if (!authorStats.some((item) => item.author === selectedAuthor)) {
      setSelectedAuthor(null)
    }
  }, [authorStats, selectedAuthor])

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase()
    const source = selectedAuthor
      ? jobs.filter((job) => (job.author?.trim() || '未知 UP') === selectedAuthor)
      : jobs
    if (!q) return source
    return source.filter((job) => {
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
  }, [jobs, debouncedQuery, selectedAuthor])

  // 筛选条件变化时，增量渲染计数回到初始，避免停留在上一个长列表的高位。
  useEffect(() => {
    setVisibleCount(INITIAL_VISIBLE)
  }, [debouncedQuery, selectedAuthor])

  const visibleJobs = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount])
  const hasMore = visibleCount < filtered.length

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisibleCount((current) => Math.min(current + VISIBLE_STEP, filtered.length))
        }
      },
      {rootMargin: '400px'},
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [filtered.length])

  const handleBack = () => {
    if (window.history.length > 1) {
      window.history.back()
      return
    }
    navigate('/')
  }

  const restoreJob = useCallback((job: Job) => {
    setJobs((current) => {
      if (current.some((item) => item.id === job.id)) return current
      return [...current, job].sort((a, b) => b.created_at - a.created_at)
    })
  }, [])

  const commitDelete = useCallback(async (jobId: string) => {
    const entry = pendingDeletes.current.get(jobId)
    if (!entry) return
    pendingDeletes.current.delete(jobId)
    try {
      await deleteJob(jobId)
    } catch (err) {
      // 404 = 后端已无此任务（如先被「清空」删掉），无需恢复，否则会把已删任务「复活」。
      if (err instanceof ApiError && err.status === 404) return
      restoreJob(entry.job)
      toast.error('删除失败', err instanceof Error ? err.message : '请重试')
    }
  }, [restoreJob, toast])

  const handleDelete = (jobId: string) => {
    const job = jobs.find((item) => item.id === jobId)
    if (!job) return
    // 进行中任务后端会 409 拒删，不走乐观移除/撤销（否则行会先消失再弹回），直接提示。
    if (isRunning(job.status)) {
      void deleteJob(jobId).catch((err) =>
        toast.error('删除失败', err instanceof Error ? err.message : '请先取消再删除'),
      )
      return
    }
    // 乐观移除，先从列表消失；撤销窗口内点「撤销」可恢复，否则到点提交后端。
    setJobs((current) => current.filter((item) => item.id !== jobId))
    const timer = window.setTimeout(() => void commitDelete(jobId), UNDO_WINDOW_MS)
    pendingDeletes.current.set(jobId, {timer, job})
    toast.success('已删除', undefined, {
      taskName: job.title || undefined,
      durationMs: UNDO_WINDOW_MS,
      action: {
        label: '撤销',
        onClick: () => {
          const entry = pendingDeletes.current.get(jobId)
          if (!entry) return
          window.clearTimeout(entry.timer)
          pendingDeletes.current.delete(jobId)
          restoreJob(entry.job)
        },
      },
    })
  }

  const handleClearCompleted = async () => {
    setClearing(true)
    // 清空前结清撤销窗口内的待删任务：清掉计时器，交给 deleteAll + reload 兜底，
    // 避免计时器稍后触发 commitDelete 与全量删除竞争。
    for (const entry of pendingDeletes.current.values()) {
      window.clearTimeout(entry.timer)
    }
    pendingDeletes.current.clear()
    try {
      const response = await deleteAllJobs()
      const detail = response.skipped_count > 0
        ? `已删除 ${response.deleted_count} 个，跳过 ${response.skipped_count} 个进行中任务`
        : `已删除 ${response.deleted_count} 个`
      toast.success('已清理', detail)
      setConfirmClearOpen(false)
      await loadFirstPage()
    } catch (err) {
      toast.error('清理失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="grid min-h-[calc(100dvh-3rem)] content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
      <header className="grid gap-4 px-4 sm:px-5">
        <button
          type="button"
          onClick={handleBack}
          className="inline-flex min-h-10 w-fit items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
        >
          <ArrowLeft size={16} />
          返回
        </button>
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">历史记录</h1>
            <p className="mt-1 text-sm text-muted">查看、搜索和清理已经创建的摘要任务。</p>
          </div>
          <IconTooltip label="新建" className="shrink-0">
            <Link
              href="/"
              aria-label="新建"
              title="新建"
              className="grid h-11 w-11 place-items-center rounded-2xl bg-brand text-white shadow-card transition-[transform,filter] hover:brightness-105 active:scale-95"
            >
              <Plus size={18} />
            </Link>
          </IconTooltip>
        </div>
      </header>

      <section className="min-w-0 px-4 sm:px-5">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-y border-line/70 py-3">
          <label className="relative block min-w-0">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
            />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜标题 / UP 主 / BVID"
              className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30"
            />
          </label>
          <IconTooltip label="清空已完成">
            <button
              type="button"
              aria-label="清空已完成"
              title="清空已完成 / 失败 / 取消的任务"
              onClick={() => setConfirmClearOpen(true)}
              disabled={clearing || jobs.length === 0}
              className="grid h-11 w-11 place-items-center rounded-2xl bg-lift text-muted transition-[transform,background-color,color] hover:bg-danger/10 hover:text-danger active:scale-95 disabled:opacity-40"
            >
              <Trash size={16} className={clearing ? 'animate-pulse' : undefined} />
            </button>
          </IconTooltip>
        </div>

        {!loading && !loadError && authorStats.length > 0 && (
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 pt-3 sm:-mx-5 sm:px-5">
            <button
              type="button"
              onClick={() => setSelectedAuthor(null)}
              className={`inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-[transform,background-color,color] active:scale-95 ${
                selectedAuthor == null
                  ? 'bg-brand text-white shadow-card'
                  : 'bg-lift text-muted hover:bg-line/70 hover:text-ink'
              }`}
            >
              全部
              <span className={selectedAuthor == null ? 'text-white/80' : 'text-muted'}>
                {jobs.length}
              </span>
            </button>
            {authorStats.map((item) => (
              <button
                key={item.author}
                type="button"
                onClick={() => setSelectedAuthor((current) => (current === item.author ? null : item.author))}
                className={`inline-flex min-h-9 max-w-[14rem] shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-[transform,background-color,color] active:scale-95 ${
                  selectedAuthor === item.author
                    ? 'bg-brand text-white shadow-card'
                    : 'bg-lift text-muted hover:bg-line/70 hover:text-ink'
                }`}
                title={`${item.author} · ${item.count}`}
              >
                <span className="truncate">{item.author}</span>
                <span className={selectedAuthor === item.author ? 'text-white/80' : 'text-muted'}>
                  {item.count}
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="py-3">
          {loading && (
            <ul className="grid gap-2">
              {Array.from({length: 6}).map((_, index) => (
                <SkeletonRow key={index} />
              ))}
            </ul>
          )}

          {!loading && loadError && (
            <div className="grid justify-items-center gap-3 border-b border-line/60 py-12 text-center">
              <p className="text-sm text-muted">加载失败，请检查网络后重试</p>
              <button
                type="button"
                onClick={() => void loadFirstPage()}
                className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
              >
                <RotateCw size={15} />
                重试
              </button>
            </div>
          )}

          {!loading && !loadError && jobs.length === 0 && (
            <div className="grid justify-items-center gap-3 border-b border-line/60 py-12 text-center">
              <p className="text-sm text-muted">还没有任务记录</p>
              <Link
                href="/"
                className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-brand px-4 text-sm font-medium text-white shadow-card transition-[transform,filter] hover:brightness-105 active:scale-95"
              >
                <Plus size={15} />
                新建一个
              </Link>
            </div>
          )}

          {!loading && !loadError && jobs.length > 0 && filtered.length === 0 && (
            <p className="border-b border-line/60 py-12 text-center text-sm text-muted">
              没有匹配{selectedAuthor ? `「${selectedAuthor}」` : ''}{debouncedQuery ? `「${debouncedQuery}」` : ''}的记录
            </p>
          )}

          {!loading && !loadError && filtered.length > 0 && (
            <>
              <ul className="grid gap-2">
                {visibleJobs.map((job) => {
                  const running = isRunning(job.status)
                  return (
                    <li
                      key={job.id}
                      className="group/item grid grid-cols-[minmax(0,1fr)_2.75rem] items-start gap-2 rounded-2xl bg-lift/55 p-2 transition-[background-color,box-shadow] hover:bg-brandSoft/30"
                    >
                      <div className="min-w-0 px-2 py-1.5">
                        <Link
                          href={`/jobs/${job.id}`}
                          className="block transition-[transform] active:scale-[0.99]"
                        >
                          <p className="line-clamp-2 break-words text-sm font-medium text-ink">
                            {job.title || job.url}
                          </p>
                        </Link>
                        {/* 作者是独立可点链接（不能套在上面的任务 Link 里——anchor 不能嵌 anchor）。 */}
                        <p className="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted">
                          <AuthorLink job={job} />
                          <span className="shrink-0">· {formatDuration(job.duration)}</span>
                        </p>
                        <Link href={`/jobs/${job.id}`} className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                          <span
                            className={`rounded-full px-2 py-0.5 ${
                              job.status === 'COMPLETED'
                                ? 'bg-brandSoft text-brand'
                                : job.status === 'FAILED'
                                  ? 'bg-danger/15 text-danger'
                                  : running
                                    ? 'bg-warning/15 text-warning'
                                    : 'bg-panel text-muted'
                            }`}
                          >
                            {formatStatus(job.status)}
                          </span>
                          <span className="text-muted">{formatDate(job.created_at)}</span>
                        </Link>
                      </div>
                      <IconTooltip label="删除">
                        <button
                          type="button"
                          aria-label="删除"
                          title="删除"
                          onClick={() => handleDelete(job.id)}
                          className="grid h-11 w-11 place-items-center rounded-xl text-muted transition-[transform,background-color,color] hover:bg-panel hover:text-danger active:scale-95 sm:opacity-0 sm:group-hover/item:opacity-100 sm:focus-visible:opacity-100"
                        >
                          <Trash2 size={16} />
                        </button>
                      </IconTooltip>
                    </li>
                  )
                })}
              </ul>
              {hasMore && <div ref={sentinelRef} aria-hidden className="h-8" />}
            </>
          )}
        </div>
      </section>

      <ConfirmDialog
        open={confirmClearOpen}
        title="清空已完成的任务？"
        description="将删除所有已完成 / 已失败 / 已取消的任务，进行中任务不受影响。此操作无法撤销。"
        confirmLabel="清空"
        danger
        loading={clearing}
        onConfirm={() => void handleClearCompleted()}
        onCancel={() => setConfirmClearOpen(false)}
      />
    </div>
  )
}
