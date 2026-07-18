import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {RotateCw, Search} from 'lucide-react'
import {getLatestDistillRun, getUpVideos, createJob, type DistillRun, type JobStatus, type UpOrder, type UpVideo} from '../../lib/api'
import {isRunning} from '../../lib/jobStatus'
import {useRuntimeConfig} from '../../hooks/useRuntimeConfig'
import {Spinner} from '../../components/Spinner'
import {Skeleton} from '../../components/Skeleton'
import {DistillPanel} from '../../components/DistillPanel'
import {useToast} from '../../components/ToastProvider'
import {BackButton} from '../UpPage'
import {DistillButton} from './DistillButton'
import {VideoRow} from './VideoRow'

type Filter = 'all' | 'todo' | 'done'

export function UpList({mid}: {mid: number}) {
  const toast = useToast()
  const runtime = useRuntimeConfig()
  const [videos, setVideos] = useState<UpVideo[]>([])
  const [author, setAuthor] = useState('')
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [order, setOrder] = useState<UpOrder>('pubdate')
  // 一键总结后的乐观覆盖：bvid -> {status, job_id}，不刷新就能立刻显示「进行中」。
  const [overrides, setOverrides] = useState<Record<string, {status: JobStatus; job_id: string}>>({})
  const [summarizing, setSummarizing] = useState<Set<string>>(new Set())
  // 蒸馏语料：null=没有 run（展示按钮），非 null=展示进度面板。distillChecked 之前
  // 先不渲染按钮/面板，避免"先闪一下按钮再切成面板"。
  const [distillRun, setDistillRun] = useState<DistillRun | null>(null)
  const [distillChecked, setDistillChecked] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [query])

  const fetchPage = useCallback(
    async (pageNum: number, keyword: string, sortOrder: UpOrder, mode: 'reset' | 'append') => {
      if (mode === 'reset') setLoading(true)
      else setLoadingMore(true)
      setError(null)
      try {
        const res = await getUpVideos(mid, {page: pageNum, keyword, order: sortOrder})
        // 空结果页（如搜索无命中）author 为空时保留上一次的昵称。
        setAuthor((prev) => res.author || prev)
        setTotal(res.total)
        setPage(res.page)
        setHasMore(res.has_more)
        setVideos((current) => (mode === 'reset' ? res.videos : [...current, ...res.videos]))
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载失败，请检查网络后重试')
        if (mode === 'reset') setVideos([])
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [mid],
  )

  // mid / 搜索词 / 排序变化 → 重置到第一页。
  useEffect(() => {
    void fetchPage(1, debouncedQuery, order, 'reset')
  }, [fetchPage, debouncedQuery, order])

  // 进页面先查一次有没有正在跑（或已跑完/失败）的蒸馏 run，有就直接展示面板而不是按钮。
  useEffect(() => {
    let cancelled = false
    setDistillChecked(false)
    setDistillRun(null)
    void getLatestDistillRun(mid)
      .then((res) => {
        if (!cancelled) setDistillRun(res.run)
      })
      .catch(() => {
        // 查询失败就当没有 run 处理，回退成按钮；真要启动时后端仍会用 409 兜底。
      })
      .finally(() => {
        if (!cancelled) setDistillChecked(true)
      })
    return () => {
      cancelled = true
    }
  }, [mid])

  // 滚到底自动加载下一页。
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loading && !loadingMore) {
          void fetchPage(page + 1, debouncedQuery, order, 'append')
        }
      },
      {rootMargin: '400px'},
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [fetchPage, hasMore, loading, loadingMore, page, debouncedQuery, order])

  const effectiveStatus = useCallback(
    (video: UpVideo): JobStatus | null => overrides[video.bvid]?.status ?? video.status,
    [overrides],
  )
  const jobIdOf = useCallback(
    (video: UpVideo): string | null => overrides[video.bvid]?.job_id ?? video.job_id,
    [overrides],
  )

  const visible = useMemo(() => {
    if (filter === 'all') return videos
    return videos.filter((video) => {
      const status = effectiveStatus(video)
      if (filter === 'done') return status === 'COMPLETED'
      return status !== 'COMPLETED' && !(status && isRunning(status)) // todo：未完成且非进行中
    })
  }, [videos, filter, effectiveStatus])

  const summarize = async (video: UpVideo) => {
    setSummarizing((s) => new Set(s).add(video.bvid))
    try {
      const options: {task_type: 'summary'; email_enabled?: boolean} = {task_type: 'summary'}
      if (runtime?.email_configured) options.email_enabled = true
      const res = await createJob(video.url, options)
      setOverrides((o) => ({
        ...o,
        [video.bvid]: {status: res.deduped ? 'COMPLETED' : 'PENDING', job_id: res.job_id},
      }))
      toast.success(res.deduped ? '这条之前总结过，已复用' : '已开始总结', undefined, {taskName: video.title})
    } catch (err) {
      toast.error('总结失败', err instanceof Error ? err.message : '请稍后再试', {taskName: video.title})
    } finally {
      setSummarizing((s) => {
        const next = new Set(s)
        next.delete(video.bvid)
        return next
      })
    }
  }

  const counts = useMemo(() => {
    let done = 0
    let todo = 0
    for (const video of videos) {
      const status = effectiveStatus(video)
      if (status === 'COMPLETED') done += 1
      else if (!status || !isRunning(status)) todo += 1
    }
    return {done, todo}
  }, [videos, effectiveStatus])

  return (
    <div className="grid animate-fade-in-up content-start gap-5">
      <header className="grid gap-4 px-4 sm:px-5">
        <BackButton />
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">
              {author || `UP ${mid}`}
            </h1>
            <p className="mt-1 text-sm text-muted">
              共 {total} 条投稿{videos.length > 0 && ` · 已加载 ${videos.length}`}
            </p>
          </div>
          {distillChecked && !distillRun && <DistillButton mid={mid} onStarted={setDistillRun} />}
        </div>
        {distillChecked && distillRun && (
          <DistillPanel key={distillRun.id} mid={mid} run={distillRun} onRunChange={setDistillRun} />
        )}
      </header>

      <section className="min-w-0 px-4 sm:px-5">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-y border-line/70 py-3">
          <label className="relative block min-w-0">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="在该 UP 的投稿里搜标题"
              className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30"
            />
          </label>
          <div className="flex gap-1 rounded-2xl bg-lift p-1 text-xs">
            {(
              [
                ['all', '全部'],
                ['todo', `未总结${counts.todo ? ` ${counts.todo}` : ''}`],
                ['done', `已总结${counts.done ? ` ${counts.done}` : ''}`],
              ] as Array<[Filter, string]>
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`min-h-9 whitespace-nowrap rounded-xl px-3 transition-[background-color,color] ${
                  filter === key ? 'bg-brand text-white shadow-card' : 'text-muted hover:text-ink'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 text-xs text-muted">
          <span>排序</span>
          <div className="flex gap-1 rounded-2xl bg-lift p-1">
            {(
              [
                ['pubdate', '最新'],
                ['click', '最热'],
              ] as Array<[UpOrder, string]>
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setOrder(key)}
                className={`min-h-8 rounded-xl px-3 transition-[background-color,color] ${
                  order === key ? 'bg-brand text-white shadow-card' : 'text-muted hover:text-ink'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="py-3">
          {loading && <Skeleton count={6} />}

          {!loading && error && (
            <div className="grid justify-items-center gap-3 py-12 text-center">
              <p className="text-sm text-muted">{error}</p>
              <button
                type="button"
                onClick={() => void fetchPage(1, debouncedQuery, order, 'reset')}
                className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition hover:bg-line/70 hover:text-ink active:scale-95"
              >
                <RotateCw size={15} />
                重试
              </button>
            </div>
          )}

          {!loading && !error && visible.length === 0 && (
            <p className="py-12 text-center text-sm text-muted">没有符合条件的投稿</p>
          )}

          {!loading && !error && visible.length > 0 && (
            <>
              <ul className="grid gap-2">
                {visible.map((video, index) => (
                  <VideoRow
                    key={video.bvid}
                    video={video}
                    status={effectiveStatus(video)}
                    jobId={jobIdOf(video)}
                    busy={summarizing.has(video.bvid)}
                    onSummarize={() => void summarize(video)}
                    index={index}
                  />
                ))}
              </ul>
              {hasMore && filter === 'all' && (
                <div ref={sentinelRef} aria-hidden className="h-8" />
              )}
              {loadingMore && (
                <div className="flex items-center justify-center gap-2 py-4 text-xs text-muted">
                  <Spinner size={14} />
                  加载更多…
                </div>
              )}
              {hasMore && filter !== 'all' && (
                <p className="py-4 text-center text-xs text-muted">
                  筛选只作用于已加载的 {videos.length} 条；切到「全部」可继续加载
                </p>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  )
}
