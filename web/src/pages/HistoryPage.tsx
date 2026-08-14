import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {ChevronLeft, ChevronRight, MoreHorizontal, Plus, RotateCw, Search, Trash2} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {
  ApiError, executeBulkDelete, previewBulkDelete, deleteJob, listJobs, resummarizeJob,
  type BulkDeletePreview, type BulkDeleteQuery, type Job, type JobOptionOverrides,
} from '../lib/api'
import {writeActive} from '../lib/activeJob'
import {formatDate, formatDuration, formatStatus} from '../lib/format'
import {isRunning} from '../lib/jobStatus'
import {AuthorLink} from '../components/AuthorLink'
import {BackButton} from '../components/BackButton'
import {Skeleton} from '../components/Skeleton'
import {useToast} from '../components/ToastProvider'
import {ConfirmDialog} from '../components/ConfirmDialog'
import {useRuntimeConfig} from '../hooks/useRuntimeConfig'
import {IconTooltip} from './history/IconTooltip'
import {UsageStrip} from './history/UsageStrip'

const PAGE_SIZE = 60
const UNDO_WINDOW_MS = 5000
const HISTORY_RESTORE_KEY = 'biri-youyaku.history.restore.v2'

function opaqueHistoryCursor(cursor: string | number | null | undefined) {
  return typeof cursor === 'string' ? cursor : null
}

function jobWeekStart(job: Job) {
  const date = new Date(job.completed_at ?? job.created_at)
  date.setHours(0, 0, 0, 0)
  const weekday = (date.getDay() + 6) % 7
  date.setDate(date.getDate() - weekday)
  return date.getTime()
}

function dayKey(ms: number) {
  const date = new Date(ms)
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function weekLabel(weekStart: number) {
  const start = new Date(weekStart)
  const end = new Date(weekStart)
  end.setDate(end.getDate() + 6)
  const formatter = new Intl.DateTimeFormat('zh-CN', {month: 'numeric', day: 'numeric'})
  return `${formatter.format(start)}—${formatter.format(end)}`
}

function dayLabel(ms: number) {
  const date = new Date(ms)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  if (date.toDateString() === today.toDateString()) return '今天'
  if (date.toDateString() === yesterday.toDateString()) return '昨天'
  return new Intl.DateTimeFormat('zh-CN', {month: 'numeric', day: 'numeric', weekday: 'short'}).format(date)
}

interface WeekGroup {weekStart: number; jobs: Job[]}

interface HistoryRestoreSnapshot {
  query: string
  selectedWeek: number | null
  loadedPages: number
  nextCursor: string | null
  scrollY: number
  anchorJobId: string | null
  anchorWeek: number | null
}

function readHistoryRestore(): HistoryRestoreSnapshot | null {
  try {
    const raw = window.sessionStorage.getItem(HISTORY_RESTORE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<HistoryRestoreSnapshot>
    if (typeof value.query !== 'string' || typeof value.loadedPages !== 'number') return null
    return {
      query: value.query,
      selectedWeek: typeof value.selectedWeek === 'number' ? value.selectedWeek : null,
      loadedPages: Math.max(1, value.loadedPages),
      nextCursor: typeof value.nextCursor === 'string' ? value.nextCursor : null,
      scrollY: typeof value.scrollY === 'number' ? value.scrollY : 0,
      anchorJobId: typeof value.anchorJobId === 'string' ? value.anchorJobId : null,
      anchorWeek: typeof value.anchorWeek === 'number' ? value.anchorWeek : null,
    }
  } catch {
    return null
  }
}

export function HistoryPage() {
  const [, navigate] = useLocation()
  const [restoreSnapshot] = useState(readHistoryRestore)
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<'initial' | 'partial' | null>(null)
  const [query, setQuery] = useState(() => restoreSnapshot?.query ?? '')
  const [debouncedQuery, setDebouncedQuery] = useState(() => restoreSnapshot?.query ?? '')
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [selectedWeek, setSelectedWeek] = useState<number | null>(() => {
    if (restoreSnapshot?.selectedWeek != null) return restoreSnapshot.selectedWeek
    if (restoreSnapshot?.anchorWeek != null) return restoreSnapshot.anchorWeek
    return null
  })
  const [moreOpen, setMoreOpen] = useState(false)
  const [deletePreview, setDeletePreview] = useState<BulkDeletePreview | null>(null)
  // 弹窗只使用发起预览时的筛选快照；用户随后改筛选不会误导确认文案。
  const [deletePreviewFilters, setDeletePreviewFilters] = useState<BulkDeleteQuery | null>(null)
  const [previewingDelete, setPreviewingDelete] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [resummaryTarget, setResummaryTarget] = useState<Job | null>(null)
  const [resummarizing, setResummarizing] = useState(false)
  const toast = useToast()
  const runtime = useRuntimeConfig()
  const pendingDeletes = useRef<Map<string, {timer: number; job: Job}>>(new Map())
  const loadGenerationRef = useRef(0)
  const activeLoadRef = useRef<{controller: AbortController; generation: number} | null>(null)
  const nextCursorRef = useRef<string | null>(null)
  const loadedPagesRef = useRef(restoreSnapshot?.loadedPages ?? 1)
  const restoreSnapshotRef = useRef(restoreSnapshot)
  const restoredScrollRef = useRef(false)

  const invalidateLoad = useCallback(() => {
    loadGenerationRef.current += 1
    activeLoadRef.current?.controller.abort()
    activeLoadRef.current = null
  }, [])

  const historyFilters = useMemo(() => ({
    query: debouncedQuery.trim() || undefined,
  }), [debouncedQuery])

  const loadFirstPage = useCallback(async () => {
    invalidateLoad()
    const load = {controller: new AbortController(), generation: loadGenerationRef.current}
    activeLoadRef.current = load
    const isCurrent = () => activeLoadRef.current === load && loadGenerationRef.current === load.generation
    setLoading(true)
    // A prior page request may belong to the previous filter generation. Its
    // guarded finally must not leave the new result set stuck as loading.
    setLoadingMore(false)
    setLoadError(null)
    try {
      const [response, activeResponse] = await Promise.all([
        listJobs({limit: PAGE_SIZE, terminal_only: true, ...historyFilters}, {signal: load.controller.signal}),
        listJobs({active_only: true, ...historyFilters}, {signal: load.controller.signal}),
      ])
      if (!isCurrent()) return
      const restore = restoreSnapshotRef.current
      const restoringPages = restore && restore.query === (historyFilters.query ?? '')
        ? restore.loadedPages
        : 1
      let restoredJobs = response.jobs
      let restoredCursor = opaqueHistoryCursor(response.next_cursor)
      let loadedPages = 1
      while (restoredCursor && loadedPages < restoringPages) {
        const nextPage = await listJobs({limit: PAGE_SIZE, cursor: restoredCursor, terminal_only: true, ...historyFilters}, {signal: load.controller.signal})
        if (!isCurrent()) return
        const known = new Set(restoredJobs.map((job) => job.id))
        restoredJobs = [...restoredJobs, ...nextPage.jobs.filter((job) => !known.has(job.id))]
        restoredCursor = opaqueHistoryCursor(nextPage.next_cursor)
        loadedPages += 1
      }
      const known = new Set(activeResponse.jobs.map((job) => job.id))
      setJobs([...activeResponse.jobs, ...restoredJobs.filter((job) => !known.has(job.id))])
      loadedPagesRef.current = loadedPages
      nextCursorRef.current = restoredCursor
      setNextCursor(nextCursorRef.current)
    } catch {
      if (!isCurrent() || load.controller.signal.aborted) return
      setJobs([])
      loadedPagesRef.current = 1
      nextCursorRef.current = null
      setNextCursor(null)
      setLoadError('initial')
    } finally {
      if (isCurrent()) setLoading(false)
    }
  }, [historyFilters, invalidateLoad])

  const loadMore = useCallback(async () => {
    const cursor = nextCursorRef.current
    if (!cursor || loadingMore || loading) return
    const generation = loadGenerationRef.current
    setLoadingMore(true)
    setLoadError(null)
    try {
      const response = await listJobs({limit: PAGE_SIZE, cursor, terminal_only: true, ...historyFilters})
      if (generation !== loadGenerationRef.current) return
      setJobs((current) => {
        const known = new Set(current.map((job) => job.id))
        return [...current, ...response.jobs.filter((job) => !known.has(job.id))]
      })
      loadedPagesRef.current += 1
      nextCursorRef.current = opaqueHistoryCursor(response.next_cursor)
      setNextCursor(nextCursorRef.current)
    } catch {
      if (generation === loadGenerationRef.current) setLoadError('partial')
    } finally {
      if (generation === loadGenerationRef.current) setLoadingMore(false)
    }
  }, [historyFilters, loading, loadingMore])

  useEffect(() => {
    void loadFirstPage()
    return () => invalidateLoad()
  }, [invalidateLoad, loadFirstPage])

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

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 200)
    return () => window.clearTimeout(timer)
  }, [query])

  const activeJobs = useMemo(() => jobs.filter((job) => isRunning(job.status)), [jobs])
  const weekGroups = useMemo<WeekGroup[]>(() => {
    const groups = new Map<number, Job[]>()
    for (const job of jobs) {
      if (isRunning(job.status)) continue
      const week = jobWeekStart(job)
      groups.set(week, [...(groups.get(week) ?? []), job])
    }
    return [...groups.entries()].sort(([a], [b]) => b - a).map(([weekStart, weekJobs]) => ({weekStart, jobs: weekJobs}))
  }, [jobs])
  const searchMode = Boolean(debouncedQuery.trim())
  const searchJobs = useMemo(() => jobs.filter((job) => !isRunning(job.status)), [jobs])

  useEffect(() => {
    if (weekGroups.length === 0) {
      setSelectedWeek(null)
      return
    }
    setSelectedWeek((current) => {
      if (current != null && weekGroups.some((group) => group.weekStart === current)) return current
      return weekGroups[0].weekStart
    })
  }, [weekGroups])

  const selectedGroup = useMemo(
    () => weekGroups.find((group) => group.weekStart === selectedWeek) ?? null,
    [weekGroups, selectedWeek],
  )

  const selectedWeekIndex = useMemo(
    () => weekGroups.findIndex((group) => group.weekStart === selectedWeek),
    [weekGroups, selectedWeek],
  )
  const selectedByDay = useMemo(() => {
    if (!selectedGroup) return [] as Array<[string, Job[]]>
    const byDay = new Map<string, Job[]>()
    for (const job of selectedGroup.jobs) {
      const key = dayKey(job.completed_at ?? job.created_at)
      byDay.set(key, [...(byDay.get(key) ?? []), job])
    }
    return [...byDay.entries()]
  }, [selectedGroup])

  useEffect(() => {
    const restore = restoreSnapshotRef.current
    if (!restore || loading || restoredScrollRef.current) return
    restoredScrollRef.current = true
    window.requestAnimationFrame(() => {
      if (restore.anchorJobId) {
        const anchor = document.getElementById(`history-job-${restore.anchorJobId}`)
        if (anchor) anchor.scrollIntoView({block: 'center'})
        else window.scrollTo({top: restore.scrollY})
      } else {
        window.scrollTo({top: restore.scrollY})
      }
    })
    try { window.sessionStorage.removeItem(HISTORY_RESTORE_KEY) } catch {}
    restoreSnapshotRef.current = null
  }, [jobs, loading])

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const hasMore = nextCursor != null
  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !hasMore) return
    const observer = new IntersectionObserver((entries) => {
      if (!entries[0]?.isIntersecting) return
      void loadMore()
    }, {rootMargin: '400px'})
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasMore, loadMore])

  const restoreJob = useCallback((job: Job) => setJobs((current) => current.some((item) => item.id === job.id) ? current : [...current, job].sort((a, b) => b.created_at - a.created_at)), [])
  const commitDelete = useCallback(async (jobId: string) => {
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
  }, [restoreJob, toast])
  const handleDelete = (jobId: string) => {
    const job = jobs.find((item) => item.id === jobId)
    if (!job) return
    if (isRunning(job.status)) {
      // Running jobs should be cancelled first; delete will fail if the runner
      // still holds the row, so show a toast and keep the row visible.
      toast.error('无法删除', '请先取消进行中的任务再删除')
      return
    }
    setJobs((current) => current.filter((item) => item.id !== jobId))
    const timer = window.setTimeout(() => void commitDelete(jobId), UNDO_WINDOW_MS)
    pendingDeletes.current.set(jobId, {timer, job})
    toast.success('已删除', undefined, {taskName: job.title || undefined, durationMs: UNDO_WINDOW_MS, action: {label: '撤销', onClick: () => {
      const entry = pendingDeletes.current.get(jobId)
      if (!entry) return
      window.clearTimeout(entry.timer); pendingDeletes.current.delete(jobId); restoreJob(entry.job)
    }}})
  }

  const bulkFilters = useMemo(() => ({query: debouncedQuery.trim() || undefined}), [debouncedQuery])
  const flushPendingDeletes = useCallback(async () => {
    const pendingIds = [...pendingDeletes.current.keys()]
    for (const jobId of pendingIds) {
      const entry = pendingDeletes.current.get(jobId)
      if (entry) window.clearTimeout(entry.timer)
    }
    await Promise.all(pendingIds.map((jobId) => commitDelete(jobId)))
  }, [commitDelete])
  const openDeletePreview = async () => {
    if (query !== debouncedQuery) return
    const filters = {...bulkFilters}
    setMoreOpen(false); setPreviewingDelete(true)
    try {
      // A preview must begin from a committed database state. Otherwise a
      // later bulk delete could cancel unrelated optimistic single deletes.
      await flushPendingDeletes()
      setDeletePreview(await previewBulkDelete(filters))
      setDeletePreviewFilters(filters)
    }
    catch (err) { toast.error('无法获取删除预览', err instanceof Error ? err.message : '请重试') }
    finally { setPreviewingDelete(false) }
  }
  const handleBulkDelete = async () => {
    if (!deletePreview) return
    setClearing(true)
    try {
      const response = await executeBulkDelete(deletePreview.preview_token)
      setDeletePreview(null)
      setDeletePreviewFilters(null)
      const detailBase = response.cleanup_pending_count
        ? `记录已删除，${response.cleanup_pending_count} 个文件待后台重试。`
        : `已删除 ${response.deleted_count} 条记录`
      toast.success('已删除', detailBase)
      await loadFirstPage()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        try {
          setDeletePreview(await previewBulkDelete(deletePreviewFilters ?? bulkFilters))
          toast.error('删除范围已变化', '已重新生成预览，请再次确认；未删除任何记录。')
        } catch {
          setDeletePreview(null)
          setDeletePreviewFilters(null)
          toast.error('删除范围已变化', '请重新预览后确认；未删除任何记录。')
        }
      } else {
        setDeletePreview(null)
        setDeletePreviewFilters(null)
        toast.error('删除失败', err instanceof Error ? err.message : '请重试')
      }
    } finally { setClearing(false) }
  }
  const newSummaryOptions = useCallback((): Partial<JobOptionOverrides> => ({task_type: 'summary', ...(runtime?.email_configured ? {email_enabled: true} : {})}), [runtime?.email_configured])
  const handleResummarize = async () => {
    if (!resummaryTarget) return
    setResummarizing(true)
    try { const response = await resummarizeJob(resummaryTarget.id, newSummaryOptions()); writeActive({jobId: response.job_id, url: resummaryTarget.url}); setResummaryTarget(null); toast.success('已开始重新总结'); navigate(`/jobs/${response.job_id}`) }
    catch (err) { toast.error('重新总结失败', err instanceof Error ? err.message : '请重试') }
    finally { setResummarizing(false) }
  }
  const hasFilters = Boolean(debouncedQuery.trim())
  const previewHasFilters = Boolean(deletePreviewFilters?.query)
  const queryPending = query !== debouncedQuery

  const clearFilters = () => {
    setQuery('')
    setDebouncedQuery('')
  }

  const saveHistoryState = useCallback((anchorJobId: string | null = null, anchorWeek: number | null = null) => {
    try {
      window.sessionStorage.setItem(HISTORY_RESTORE_KEY, JSON.stringify({
        query: debouncedQuery,
        selectedWeek: anchorWeek ?? selectedWeek,
        loadedPages: loadedPagesRef.current,
        nextCursor: nextCursorRef.current,
        scrollY: window.scrollY,
        anchorJobId,
        anchorWeek,
      } satisfies HistoryRestoreSnapshot))
    } catch {
      // Session storage is a convenience for back navigation; history remains usable without it.
    }
  }, [debouncedQuery, selectedWeek])

  const renderJob = (job: Job, index: number) => {
    const running = isRunning(job.status)
    return <li id={`history-job-${job.id}`} key={job.id} style={{animationDelay: `${Math.min(index, 6) * 40}ms`}} className="group/item grid animate-fade-in-up grid-cols-[minmax(0,1fr)_auto] items-start gap-2 border-b border-line/60 py-2 opacity-0 [animation-fill-mode:forwards] last:border-0">
      <div className="min-w-0">
        <Link href={`/jobs/${job.id}`} onClick={() => saveHistoryState(job.id, jobWeekStart(job))} className="block transition-[transform] active:scale-[0.99]"><p className="truncate text-sm font-medium text-ink">{job.title || job.url}</p></Link>
        <p className="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted"><AuthorLink job={job} /><span className="shrink-0">· {formatDuration(job.duration)}</span></p>
        <Link href={`/jobs/${job.id}`} onClick={() => saveHistoryState(job.id, jobWeekStart(job))} className="mt-2 flex flex-wrap items-center gap-2 text-xs"><span className={`rounded-full px-2 py-0.5 ${job.status === 'COMPLETED' ? 'bg-brandSoft text-brand' : job.status === 'FAILED' ? 'bg-danger/15 text-danger' : running ? 'bg-warning/15 text-warning' : 'bg-panel text-muted'}`}>{formatStatus(job.status)}</span><span className="text-muted">{formatDate(job.completed_at ?? job.created_at)}</span></Link>
      </div>
      <div className="flex shrink-0 gap-1 sm:opacity-0 sm:group-hover/item:opacity-100 sm:focus-within:opacity-100">
        {!running && <IconTooltip label="重新总结"><button type="button" aria-label="重新总结" onClick={() => setResummaryTarget(job)} className="grid h-11 w-11 place-items-center rounded-xl text-muted transition-[transform,background-color,color] hover:bg-lift hover:text-brand active:scale-95"><RotateCw size={16} /></button></IconTooltip>}
        <IconTooltip label="删除"><button type="button" aria-label="删除" onClick={() => handleDelete(job.id)} className="grid h-11 w-11 place-items-center rounded-xl text-muted transition-[transform,background-color,color] hover:bg-lift hover:text-danger active:scale-95"><Trash2 size={16} /></button></IconTooltip>
      </div>
    </li>
  }

  return <div className="grid min-h-[calc(100dvh-3rem)] animate-fade-in-up content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
    <header className="grid gap-4 px-4 sm:px-5">
      <BackButton />
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">历史</h1>
          <p className="mt-1 text-sm text-muted">按周查看任务，搜索、筛选或清理记录。</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <IconTooltip label="新建">
            <Link href="/" aria-label="新建" className="grid h-11 w-11 place-items-center rounded-2xl bg-brandSolid text-onBrand shadow-card"><Plus size={18} /></Link>
          </IconTooltip>
        </div>
      </div>
      <UsageStrip />
    </header>
    <section className="min-w-0 px-4 sm:px-5">
      <div className="border-y border-line/70 py-3">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
          <label className="relative block min-w-0"><Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜标题、UP 主、BVID 或标签" className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30" /></label>
          <div className="relative flex gap-2"><button type="button" aria-label="更多操作" aria-expanded={moreOpen} onClick={() => setMoreOpen((value) => !value)} disabled={previewingDelete || jobs.length === 0 || queryPending} title={queryPending ? '请等待搜索条件更新后再删除' : undefined} className="grid h-11 w-11 place-items-center rounded-2xl bg-lift text-muted hover:bg-line/70 hover:text-ink disabled:opacity-40"><MoreHorizontal size={18} /></button>{moreOpen && <div className="absolute right-0 top-12 z-30 w-56 rounded-2xl border border-line bg-panel p-2 shadow-cardHover"><button type="button" onClick={() => void openDeletePreview()} className="flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-left text-sm text-danger hover:bg-danger/10"><Trash2 size={15} />{hasFilters ? '删除筛选结果…' : '清理历史…'}</button></div>}</div>
        </div>
      </div>
      <div className="py-3">
        {loading && <Skeleton count={6} />}
        {!loading && loadError === 'initial' && <div className="grid justify-items-center gap-3 border-b border-line/60 py-12 text-center"><p className="text-sm text-muted">加载失败，请检查网络后重试</p><button type="button" onClick={() => void loadFirstPage()} className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted"><RotateCw size={15} />重试</button></div>}
        {!loading && loadError !== 'initial' && jobs.length === 0 && !hasFilters && <div className="grid justify-items-center gap-3 border-b border-line/60 py-12 text-center"><p className="text-sm text-muted">还没有任务记录</p><Link href="/" className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-brandSolid px-4 text-sm font-medium text-onBrand shadow-card"><Plus size={15} />新建一个</Link></div>}
        {!loading && loadError !== 'initial' && jobs.length === 0 && hasFilters && (
          <div className="grid justify-items-center gap-3 border-b border-line/60 py-12 text-center">
            <p className="text-sm text-muted">没有匹配的记录</p>
            <button type="button" onClick={clearFilters} className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95">清除筛选</button>
          </div>
        )}
        {!loading && loadError === 'partial' && <p role="alert" className="mb-3 text-center text-sm text-muted">部分记录加载失败，请稍后重试。</p>}
        {!loading && loadError !== 'initial' && jobs.length > 0 && <>
          {activeJobs.length > 0 && <section className="mb-4 rounded-2xl border border-warning/20 bg-warning/5 p-3"><h2 className="text-sm font-medium text-ink">进行中与等待继续 <span className="text-muted">{activeJobs.length}</span></h2><ul className="mt-2">{activeJobs.map(renderJob)}</ul></section>}
          {searchMode ? (
            <ul className="rounded-2xl bg-lift/45 px-3">{searchJobs.map(renderJob)}</ul>
          ) : (
            <div className="grid gap-3">
              {selectedGroup && (
                <section id={`history-week-${selectedGroup.weekStart}`} className="overflow-hidden rounded-2xl border border-line/70 bg-lift/45">
                  <div className="flex min-h-12 items-center gap-2 px-3">
                    <button
                      type="button"
                      aria-label="上一周"
                      disabled={selectedWeekIndex < 0 || selectedWeekIndex >= weekGroups.length - 1}
                      onClick={() => {
                        if (selectedWeekIndex < 0 || selectedWeekIndex >= weekGroups.length - 1) return
                        setSelectedWeek(weekGroups[selectedWeekIndex + 1].weekStart)
                      }}
                      className="grid h-9 w-9 place-items-center rounded-xl text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-30"
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <div className="min-w-0 flex-1 text-center">
                      <span className="text-sm font-medium text-ink">{weekLabel(selectedGroup.weekStart)}</span>
                      <span className="ml-2 text-xs text-muted">{selectedGroup.jobs.length} 条</span>
                    </div>
                    <button
                      type="button"
                      aria-label="下一周"
                      disabled={selectedWeekIndex <= 0}
                      onClick={() => {
                        if (selectedWeekIndex <= 0) return
                        setSelectedWeek(weekGroups[selectedWeekIndex - 1].weekStart)
                      }}
                      className="grid h-9 w-9 place-items-center rounded-xl text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-30"
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                  <div className="border-t border-line/60 px-3 pb-1">
                    {selectedByDay.map(([key, dayJobs]) => (
                      <div key={key}>
                        <h3 className="pt-3 text-xs font-medium text-muted">{dayLabel(dayJobs[0].completed_at ?? dayJobs[0].created_at)}</h3>
                        <ul>{dayJobs.map(renderJob)}</ul>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}
          {hasMore && <div className="grid justify-items-center gap-2 pt-3"><button type="button" onClick={() => void loadMore()} disabled={loadingMore} className="min-h-10 rounded-xl bg-lift px-4 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-50">{loadingMore ? '正在加载…' : searchMode ? '加载更多结果' : '查看更早记录'}</button><div ref={sentinelRef} aria-hidden className="h-3" /><p className="text-center text-xs text-muted">也可继续向下滚动加载</p></div>}
        </>}
      </div>
    </section>
    <ConfirmDialog
      open={deletePreview != null}
      title={previewHasFilters
        ? `永久删除当前筛选结果中的 ${deletePreview?.matched_count ?? 0} 条记录？`
        : `永久删除全部 ${deletePreview?.matched_count ?? 0} 条历史记录？`}
      description={deletePreview && <div className="grid gap-3"><div>{previewHasFilters && <><p>筛选范围</p>{deletePreviewFilters?.query && <p>搜索：“{deletePreviewFilters.query}”</p>}</>}<p>数据库中共有：{deletePreview.by_status.COMPLETED ?? 0} 条已完成 · {deletePreview.by_status.FAILED ?? 0} 条失败 · {deletePreview.by_status.CANCELED ?? 0} 条已取消</p></div><div><p className="font-medium text-ink">包括：</p>{deletePreview.sample.map((job) => <p key={job.id} className="truncate">· {job.title || '未命名视频'}{job.author ? ` · ${job.author}` : ''}</p>)}{deletePreview.sample_truncated_count > 0 && <p>另有 {deletePreview.sample_truncated_count} 条</p>}</div><p>将删除数据库中全部符合条件的记录，不仅是当前已加载或显示在屏幕中的条目。</p><p>关联的总结、字幕和音频也会永久删除。</p></div>}
      confirmLabel={`永久删除 ${deletePreview?.matched_count ?? 0} 条`}
      danger
      loading={clearing}
      onConfirm={() => void handleBulkDelete()}
      onCancel={() => { setDeletePreview(null); setDeletePreviewFilters(null) }}
    />
    <ConfirmDialog open={resummaryTarget != null} title="重新总结这个视频？" description="会复用这条记录的字幕创建一条新的总结任务，原总结会继续保留在历史记录中。" confirmLabel="重新总结" loading={resummarizing} onConfirm={() => void handleResummarize()} onCancel={() => setResummaryTarget(null)} />
  </div>
}
