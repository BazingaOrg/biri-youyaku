import {useCallback, useEffect, useMemo, useState} from 'react'
import type {ReactNode} from 'react'
import {ArrowLeft, Plus, Search, Trash, Trash2} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {deleteAllJobs, deleteJob, listJobs, type Job} from '../lib/api'
import {formatDate, formatDuration, formatStatus} from '../lib/format'
import {isRunning} from '../lib/jobStatus'
import {useToast} from '../components/ToastProvider'

const PAGE_SIZE = 200

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

export function HistoryPage() {
  const [, navigate] = useLocation()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedAuthor, setSelectedAuthor] = useState<string | null>(null)
  const [clearing, setClearing] = useState(false)
  const toast = useToast()

  const loadFirstPage = useCallback(async (cancelled?: () => boolean) => {
    setLoading(true)
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
    const q = query.trim().toLowerCase()
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
  }, [jobs, query, selectedAuthor])

  const handleBack = () => {
    if (window.history.length > 1) {
      window.history.back()
      return
    }
    navigate('/')
  }

  const handleDelete = async (jobId: string) => {
    const target = jobs.find((job) => job.id === jobId)
    try {
      await deleteJob(jobId)
      setJobs((current) => current.filter((job) => job.id !== jobId))
      toast.success('已删除', undefined, {taskName: target?.title || undefined})
    } catch (err) {
      toast.error('删除失败', err instanceof Error ? err.message : '请重试')
    }
  }

  const handleClearCompleted = async () => {
    if (!window.confirm('删除所有已完成 / 已失败 / 已取消的任务？进行中任务不受影响。')) return
    setClearing(true)
    try {
      const response = await deleteAllJobs()
      const detail = response.skipped_count > 0
        ? `已删除 ${response.deleted_count} 个，跳过 ${response.skipped_count} 个进行中任务`
        : `已删除 ${response.deleted_count} 个`
      toast.success('已清理', detail)
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
              onClick={() => void handleClearCompleted()}
              disabled={clearing || jobs.length === 0}
              className="grid h-11 w-11 place-items-center rounded-2xl bg-lift text-muted transition-[transform,background-color,color] hover:bg-danger/10 hover:text-danger active:scale-95 disabled:opacity-40"
            >
              <Trash size={16} className={clearing ? 'animate-pulse' : undefined} />
            </button>
          </IconTooltip>
        </div>

        {!loading && authorStats.length > 0 && (
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
                onClick={() => setSelectedAuthor(item.author)}
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
          {loading && <p className="border-b border-line/60 py-12 text-center text-sm text-muted">加载中</p>}
          {!loading && jobs.length === 0 && (
            <p className="border-b border-line/60 py-12 text-center text-sm text-muted">还没有任务记录</p>
          )}
          {!loading && jobs.length > 0 && filtered.length === 0 && (
            <p className="border-b border-line/60 py-12 text-center text-sm text-muted">
              没有匹配{selectedAuthor ? `「${selectedAuthor}」` : ''}{query ? `「${query}」` : ''}的记录
            </p>
          )}

          <ul className="grid gap-2">
            {filtered.map((job) => {
              const running = isRunning(job.status)
              return (
                <li
                  key={job.id}
                  className="group/item grid grid-cols-[minmax(0,1fr)_2.75rem] items-start gap-2 rounded-2xl bg-lift/55 p-2 transition-[background-color,box-shadow] hover:bg-brandSoft/30"
                >
                  <Link
                    href={`/jobs/${job.id}`}
                    className="min-w-0 rounded-xl px-2 py-1.5 text-left transition-[transform] active:scale-[0.99]"
                  >
                    <p className="line-clamp-2 break-words text-sm font-medium text-ink">
                      {job.title || job.url}
                    </p>
                    <p className="mt-1 truncate text-xs text-muted">
                      {job.author || '未知 UP'} · {formatDuration(job.duration)}
                    </p>
                    <p className="mt-2 flex flex-wrap items-center gap-2 text-xs">
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
                    </p>
                  </Link>
                  <IconTooltip label="删除">
                    <button
                      type="button"
                      aria-label="删除"
                      title="删除"
                      onClick={() => void handleDelete(job.id)}
                      className="grid h-11 w-11 place-items-center rounded-xl text-muted transition-[transform,background-color,color] hover:bg-panel hover:text-danger active:scale-95 sm:opacity-0 sm:group-hover/item:opacity-100 sm:focus-visible:opacity-100"
                    >
                      <Trash2 size={16} />
                    </button>
                  </IconTooltip>
                </li>
              )
            })}
          </ul>

        </div>
      </section>
    </div>
  )
}
