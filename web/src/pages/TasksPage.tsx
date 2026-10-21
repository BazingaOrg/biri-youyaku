import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Link} from 'wouter'
import {Trash2} from 'lucide-react'
import {ApiError, deleteJob, getJob, listJobs, type Job} from '../lib/api'
import {formatDate, formatStatus} from '../lib/format'
import {isRunning} from '../lib/jobStatus'
import {BackButton} from '../components/BackButton'
import {Button} from '../components/Button'
import {Skeleton} from '../components/Skeleton'
import {useToast} from '../components/ToastProvider'
import {IconTooltip} from './history/IconTooltip'
import {readViewState, saveViewState} from '../lib/sessionRestore'

const PAGE_SIZE = 60
const ACTIVE_REFRESH_INTERVAL_MS = 2000
const UNDO_WINDOW_MS = 5000

function opaqueCursor(cursor: string | number | null | undefined) {
  return typeof cursor === 'string' ? cursor : null
}

export function TasksPage() {
  const toast = useToast()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<'initial' | 'partial' | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const pendingDeletes = useRef<Map<string, {timer: number; job: Job}>>(new Map())
  const loadGenerationRef = useRef(0)
  const activeLoadRef = useRef<{controller: AbortController; generation: number} | null>(null)
  const activeRefreshRef = useRef<AbortController | null>(null)
  const jobsRef = useRef<Job[]>([])
  const nextCursorRef = useRef<string | null>(null)
  const loadedPagesRef = useRef(1)
  const restore = useRef(readViewState('/tasks', ''))
  const restoredScroll = useRef(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  const loadFirstPage = useCallback(async () => {
    loadGenerationRef.current += 1
    activeLoadRef.current?.controller.abort()
    const load = {controller: new AbortController(), generation: loadGenerationRef.current}
    activeLoadRef.current = load
    const isCurrent = () => activeLoadRef.current === load && loadGenerationRef.current === load.generation
    setLoading(true)
    setLoadError(null)
    try {
      const restoringPages = restore.current?.loadedPages ?? 1
      let page = await listJobs({limit: PAGE_SIZE}, {signal: load.controller.signal})
      let collected = page.jobs
      let cursor = opaqueCursor(page.next_cursor)
      let pages = 1
      while (cursor && pages < restoringPages) {
        const next = await listJobs({limit: PAGE_SIZE, cursor}, {signal: load.controller.signal})
        if (!isCurrent()) return
        const known = new Set(collected.map((job) => job.id))
        collected = [...collected, ...next.jobs.filter((job) => !known.has(job.id))]
        cursor = opaqueCursor(next.next_cursor)
        pages += 1
      }
      if (!isCurrent()) return
      setJobs(collected)
      loadedPagesRef.current = pages
      nextCursorRef.current = cursor
      setNextCursor(cursor)
    } catch {
      if (!isCurrent() || load.controller.signal.aborted) return
      setJobs([])
      setLoadError('initial')
    } finally {
      if (isCurrent()) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadFirstPage()
    return () => {
      loadGenerationRef.current += 1
      activeLoadRef.current?.controller.abort()
    }
  }, [loadFirstPage])

  useEffect(() => {
    jobsRef.current = jobs
  }, [jobs])

  const refreshActiveJobs = useCallback(async () => {
    if (loading) return
    const generation = loadGenerationRef.current
    activeRefreshRef.current?.abort()
    const controller = new AbortController()
    activeRefreshRef.current = controller
    const previousActiveIds = jobsRef.current.filter((job) => isRunning(job.status)).map((job) => job.id)
    try {
      const response = await listJobs({active_only: true}, {signal: controller.signal})
      if (controller.signal.aborted || generation !== loadGenerationRef.current) return
      const activeIds = new Set(response.jobs.map((job) => job.id))
      const terminalSnapshots = await Promise.allSettled(
        previousActiveIds
          .filter((jobId) => !activeIds.has(jobId))
          .map((jobId) => getJob(jobId, {signal: controller.signal, lite: true})),
      )
      if (controller.signal.aborted || generation !== loadGenerationRef.current) return
      const snapshots = [
        ...response.jobs,
        ...terminalSnapshots
          .filter((result): result is PromiseFulfilledResult<{ok: true; job: Job}> => result.status === 'fulfilled')
          .map((result) => result.value.job),
      ]
      const snapshotsById = new Map(snapshots.map((job) => [job.id, job]))
      setJobs((current) => {
        const knownIds = new Set(current.map((job) => job.id))
        return [
          ...current.map((job) => snapshotsById.get(job.id) ?? job),
          ...response.jobs.filter((job) => !knownIds.has(job.id)),
        ]
      })
    } catch {
      return
    } finally {
      if (activeRefreshRef.current === controller) activeRefreshRef.current = null
    }
  }, [loading])

  const activeJobs = useMemo(() => jobs.filter((job) => isRunning(job.status)), [jobs])

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'hidden') return
      void refreshActiveJobs()
    }
    const timer = activeJobs.length > 0 ? window.setInterval(refresh, ACTIVE_REFRESH_INTERVAL_MS) : undefined
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('focus', refresh)
    return () => {
      if (timer != null) window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('focus', refresh)
      activeRefreshRef.current?.abort()
    }
  }, [activeJobs.length, refreshActiveJobs])

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

  const loadMore = useCallback(async () => {
    const cursor = nextCursorRef.current
    if (!cursor || loadingMore || loading) return
    setLoadingMore(true)
    try {
      const response = await listJobs({limit: PAGE_SIZE, cursor})
      setJobs((current) => {
        const known = new Set(current.map((job) => job.id))
        return [...current, ...response.jobs.filter((job) => !known.has(job.id))]
      })
      loadedPagesRef.current += 1
      nextCursorRef.current = opaqueCursor(response.next_cursor)
      setNextCursor(nextCursorRef.current)
    } catch {
      setLoadError('partial')
    } finally {
      setLoadingMore(false)
    }
  }, [loading, loadingMore])

  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !nextCursor) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) void loadMore()
    }, {rootMargin: '400px'})
    observer.observe(node)
    return () => observer.disconnect()
  }, [loadMore, nextCursor])

  useEffect(() => {
    if (loading || restoredScroll.current) return
    restoredScroll.current = true
    const snap = restore.current
    if (snap) window.requestAnimationFrame(() => window.scrollTo({top: snap.scrollY}))
  }, [jobs, loading])

  useEffect(() => {
    return () => saveViewState('/tasks', '', {scrollY: window.scrollY, loadedPages: loadedPagesRef.current})
  }, [])

  const restoreJob = useCallback((job: Job) => {
    setJobs((current) => (current.some((item) => item.id === job.id) ? current : [job, ...current]))
  }, [])

  const commitDelete = useCallback(
    async (jobId: string) => {
      const entry = pendingDeletes.current.get(jobId)
      if (!entry) return
      pendingDeletes.current.delete(jobId)
      try {
        await deleteJob(jobId)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return
        restoreJob(entry.job)
        toast.error('删除失败', err instanceof Error ? err.message : '请重试')
      }
    },
    [restoreJob, toast],
  )

  const handleDelete = (jobId: string) => {
    const job = jobs.find((item) => item.id === jobId)
    if (!job) return
    if (isRunning(job.status)) {
      toast.error('无法删除', '请先取消进行中的任务再删除')
      return
    }
    setJobs((current) => current.filter((item) => item.id !== jobId))
    const timer = window.setTimeout(() => void commitDelete(jobId), UNDO_WINDOW_MS)
    pendingDeletes.current.set(jobId, {timer, job})
    toast.success('已删除任务记录', '笔记还在，不受影响', {
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

  return (
    <div className="mx-auto w-full max-w-5xl">
      <BackButton href="/" label="全部笔记" />
      <h1 className="mt-3 text-2xl font-semibold tracking-[-0.012em]">管理任务记录</h1>
      <p className="mt-1 text-sm text-muted">删除任务只去掉这条处理记录，已经生成的笔记还在。</p>
      <div className="mt-6">
        {loading ? <Skeleton count={6} /> : null}
        {!loading && loadError === 'initial' ? (
          <div className="grid justify-items-center gap-3 py-12 text-center">
            <p className="text-sm text-muted">加载失败，请检查网络后重试</p>
            <Button variant="secondary" onClick={() => void loadFirstPage()}>
              重试
            </Button>
          </div>
        ) : null}
        {!loading && loadError !== 'initial' && jobs.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted">还没有任务记录</p>
        ) : null}
        {!loading && jobs.length > 0 ? (
          <ul>
            {jobs.map((job) => {
              const running = isRunning(job.status)
              const failed = job.status === 'FAILED'
              return (
                <li key={job.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-b border-line py-3">
                  <div className="min-w-0">
                    <Link href={`/jobs/${job.id}`} className="block truncate text-sm font-medium hover:text-brand">
                      {job.title || job.url}
                    </Link>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-muted">
                      <span>{job.author || '未知 UP'}</span>
                      <span className="tabular-nums">{formatDate(job.updated_at ?? job.created_at)}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          failed ? 'bg-danger/15 text-danger' : running ? 'bg-brandSoft text-brand' : 'bg-lift text-muted'
                        }`}
                      >
                        {formatStatus(job.status)}
                      </span>
                    </p>
                  </div>
                  {!running ? (
                    <IconTooltip label="删除任务记录">
                      <button
                        type="button"
                        aria-label="删除"
                        onClick={() => handleDelete(job.id)}
                        className="grid h-11 w-11 place-items-center rounded-xl text-muted hover:bg-lift hover:text-danger"
                      >
                        <Trash2 size={18} />
                      </button>
                    </IconTooltip>
                  ) : null}
                </li>
              )
            })}
          </ul>
        ) : null}
        {nextCursor ? (
          <div className="grid justify-items-center gap-2 pt-4">
            <Button variant="ghost" onClick={() => void loadMore()} disabled={loadingMore}>
              {loadingMore ? '正在加载…' : '查看更早记录'}
            </Button>
            <div ref={sentinelRef} aria-hidden className="h-3" />
          </div>
        ) : null}
      </div>
    </div>
  )
}
