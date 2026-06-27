import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {ArrowLeft, Check, RotateCw, Search, Sparkles} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {createJob, getUpVideos, resolveUp, type JobStatus, type UpOrder, type UpVideo} from '../lib/api'
import {formatDay, formatDuration} from '../lib/format'
import {isRunning} from '../lib/jobStatus'
import {useRuntimeConfig} from '../hooks/useRuntimeConfig'
import {PageLoading, Spinner} from '../components/Spinner'
import {useToast} from '../components/ToastProvider'

type Filter = 'all' | 'todo' | 'done'

interface UpPageProps {
  /** /up/:mid 为 uid 字符串；/up 为 null（展示输入入口）。 */
  mid: string | null
}

export function UpPage({mid}: UpPageProps) {
  if (!mid) return <UpEntry />
  const numeric = Number(mid)
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return (
      <div className="grid min-h-[40vh] place-items-center gap-3 px-4 text-center">
        <p className="text-sm text-muted">无效的 UP 主 UID</p>
        <BackButton />
      </div>
    )
  }
  return <UpList key={mid} mid={numeric} />
}

/** /up：粘贴主页链接 / UID → 解析 → 跳 /up/:mid。 */
function UpEntry() {
  const [, navigate] = useLocation()
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    const input = value.trim()
    if (!input) return
    setBusy(true)
    setError(null)
    try {
      const {mid} = await resolveUp(input)
      navigate(`/up/${mid}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '解析失败，换个链接或直接填 UID')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-[60vh] place-items-center px-4">
      <div className="grid w-full max-w-md gap-4">
        <BackButton />
        <h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink">按 UP 主浏览投稿</h1>
        <p className="text-sm text-muted">粘贴 UP 主页链接（space.bilibili.com/…）、UID，或任意一条该 UP 的视频链接。</p>
        <input
          type="text"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setError(null)
          }}
          onKeyDown={(e) => e.key === 'Enter' && void submit()}
          placeholder="https://space.bilibili.com/123456 或 123456"
          className="min-h-11 w-full rounded-2xl bg-lift px-4 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || value.trim().length === 0}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-brand px-4 text-sm font-medium text-white shadow-card transition-[transform,filter] hover:brightness-105 active:scale-95 disabled:opacity-40"
        >
          {busy ? <RotateCw size={16} className="animate-spin" /> : <Search size={16} />}
          查看投稿
        </button>
      </div>
    </div>
  )
}

function BackButton() {
  const [, navigate] = useLocation()
  const onBack = () => {
    if (window.history.length > 1) window.history.back()
    else navigate('/')
  }
  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex min-h-10 w-fit items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
    >
      <ArrowLeft size={16} />
      返回
    </button>
  )
}

function UpList({mid}: {mid: number}) {
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
        setError(err instanceof Error ? err.message : '加载失败，请稍后再试')
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
    <div className="grid content-start gap-5">
      <header className="grid gap-4 px-4 sm:px-5">
        <BackButton />
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">
            {author || `UP ${mid}`}
          </h1>
          <p className="mt-1 text-sm text-muted">
            共 {total} 条投稿{videos.length > 0 && ` · 已加载 ${videos.length}`}
          </p>
        </div>
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
          {loading && <PageLoading label="加载投稿…" />}

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
                {visible.map((video) => (
                  <VideoRow
                    key={video.bvid}
                    video={video}
                    status={effectiveStatus(video)}
                    jobId={jobIdOf(video)}
                    busy={summarizing.has(video.bvid)}
                    onSummarize={() => void summarize(video)}
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

function VideoRow({
  video,
  status,
  jobId,
  busy,
  onSummarize,
}: {
  video: UpVideo
  status: JobStatus | null
  jobId: string | null
  busy: boolean
  onSummarize: () => void
}) {
  const done = status === 'COMPLETED'
  const running = status != null && isRunning(status)
  const failed = status === 'FAILED' || status === 'CANCELED'

  return (
    <li className="grid grid-cols-[7.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl bg-lift/55 p-2 transition-[background-color] hover:bg-brandSoft/30">
      <div className="relative aspect-video overflow-hidden rounded-xl bg-panel">
        {video.cover && (
          <img
            src={video.cover}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = 'none'
            }}
          />
        )}
        <span className="absolute bottom-1 right-1 rounded bg-ink/70 px-1 text-[10px] font-medium text-canvas">
          {formatDuration(video.duration)}
        </span>
      </div>

      <div className="min-w-0">
        <a
          href={video.url}
          target="_blank"
          rel="noreferrer"
          className="line-clamp-2 break-words text-sm font-medium text-ink hover:text-brand"
        >
          {video.title}
        </a>
        <p className="mt-1 truncate text-xs text-muted">{formatDay(video.pubdate * 1000)}</p>
      </div>

      <div className="flex items-center justify-end">
        {done ? (
          <Link
            href={`/jobs/${jobId}`}
            className="inline-flex min-h-9 items-center gap-1 rounded-xl bg-brandSoft px-3 text-xs font-medium text-brand transition hover:brightness-95 active:scale-95"
          >
            <Check size={14} />
            查看
          </Link>
        ) : running && jobId ? (
          <Link
            href={`/jobs/${jobId}`}
            className="inline-flex min-h-9 items-center gap-1 rounded-xl bg-warning/15 px-3 text-xs font-medium text-warning transition hover:brightness-95 active:scale-95"
          >
            <RotateCw size={13} className="animate-spin" />
            进行中
          </Link>
        ) : (
          <button
            type="button"
            onClick={onSummarize}
            disabled={busy}
            title={failed ? '上次未完成，重新总结' : undefined}
            className="inline-flex min-h-9 items-center gap-1 rounded-xl bg-brand px-3 text-xs font-medium text-white shadow-card transition hover:brightness-105 active:scale-95 disabled:opacity-50"
          >
            {busy ? <RotateCw size={13} className="animate-spin" /> : <Sparkles size={14} />}
            {failed ? '重试' : '总结'}
          </button>
        )}
      </div>
    </li>
  )
}
