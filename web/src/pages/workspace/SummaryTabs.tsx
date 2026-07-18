import {lazy, Suspense, useEffect, useMemo, useRef, useState} from 'react'
import ReactMarkdown from 'react-markdown'
import {Search} from 'lucide-react'
import type {Job} from '../../lib/api'
import {parseHeadings} from '../../lib/markdown'
import {formatDuration} from '../../lib/format'
import {PageLoading} from '../../components/Spinner'

// 懒加载：mind-elixir 体积不小，只有点开「脑图」tab 才拉它的 chunk + CSS。
const MindmapView = lazy(() => import('./MindmapView').then((m) => ({default: m.MindmapView})))

type Tab = 'notes' | 'mindmap' | 'transcript'

export const PROSE =
  'prose prose-sm max-w-none break-words text-ink dark:prose-invert prose-headings:tracking-[-0.012em] prose-a:text-brand [&_pre]:overflow-x-auto [&_table]:block [&_table]:overflow-x-auto [&_code]:break-all'

export function SummaryTabs({job}: {job: Job}) {
  const summary = job.summary ?? ''
  const hasTranscript = (job.transcript?.length ?? 0) > 0
  const [tab, setTab] = useState<Tab>('notes')

  const tabs: Array<[Tab, string]> = [
    ['notes', '笔记'],
    ['mindmap', '脑图'],
  ]
  if (hasTranscript) tabs.push(['transcript', '字幕原文'])

  return (
    <section className="min-w-0 w-full rounded-3xl bg-panel p-4 shadow-card sm:p-5">
      <div className="mb-4 inline-flex gap-1 rounded-2xl bg-lift p-1 text-sm">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`min-h-9 rounded-xl px-4 transition-[background-color,color] ${
              tab === key ? 'bg-brand text-white shadow-card' : 'text-muted hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div key={tab} className="animate-fade-in-up">
        {tab === 'notes' &&
          (summary ? <NotesView markdown={summary} /> : <p className="text-sm text-muted">没有总结内容</p>)}
        {tab === 'mindmap' &&
          (summary ? (
            <Suspense fallback={<PageLoading label="加载脑图…" />}>
              <MindmapView markdown={summary} title={job.title} />
            </Suspense>
          ) : (
            <p className="text-sm text-muted">没有可生成脑图的内容</p>
          ))}
        {tab === 'transcript' && hasTranscript && <TranscriptList job={job} />}
      </div>
    </section>
  )
}

/** 笔记 + 桌面端 TOC 侧边栏（滚动高亮 + 点击跳转，双向）。 */
function NotesView({markdown}: {markdown: string}) {
  const headings = useMemo(() => parseHeadings(markdown), [markdown])
  const containerRef = useRef<HTMLDivElement>(null)
  const [activeIdx, setActiveIdx] = useState(0)

  useEffect(() => {
    const root = containerRef.current
    if (!root) return
    const els = Array.from(root.querySelectorAll('h2, h3')) as HTMLElement[]
    els.forEach((el, i) => {
      el.id = `sec-${i}`
      el.style.scrollMarginTop = '16px'
    })
    if (els.length === 0) return
    // 滚动高亮：观察每个标题是否穿过视口顶部附近的一条窄带，取当前穿过带内/上方最近的标题为激活项。
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          const idx = els.indexOf(entry.target as HTMLElement)
          if (idx !== -1) setActiveIdx(idx)
        }
      },
      {rootMargin: '-96px 0px -80% 0px', threshold: 0},
    )
    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [markdown])

  const jumpTo = (i: number) => {
    const el = document.getElementById(`sec-${i}`)
    if (!el) return
    const top = el.getBoundingClientRect().top + window.scrollY - 16
    window.scrollTo({top, behavior: 'smooth'})
  }

  const showToc = headings.length >= 3
  return (
    <div className={showToc ? 'lg:grid lg:grid-cols-[minmax(0,1fr)_11rem] lg:gap-6' : ''}>
      <div ref={containerRef} className={`min-w-0 ${PROSE}`}>
        <ReactMarkdown>{markdown}</ReactMarkdown>
      </div>
      {showToc && (
        <nav aria-label="目录" className="hidden self-start lg:sticky lg:top-4 lg:block">
          <p className="mb-2 px-2 text-xs font-medium text-muted">目录</p>
          <ul className="grid gap-0.5 border-l border-line">
            {headings.map((h, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => jumpTo(i)}
                  className={`-ml-px block w-full border-l-2 py-1 text-left text-xs transition-colors ${
                    h.level === 3 ? 'pl-5' : 'pl-3'
                  } ${
                    activeIdx === i
                      ? 'border-brand font-medium text-brand'
                      : 'border-transparent text-muted hover:text-ink'
                  }`}
                  title={h.text}
                >
                  <span className="line-clamp-2">{h.text}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  )
}

/** 字幕原文 + 时间戳点击跳 B 站 ?t=秒。 */
function TranscriptList({job}: {job: Job}) {
  const lines = job.transcript ?? []
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return lines
    return lines.filter((line) => (line.text ?? '').toLowerCase().includes(q))
  }, [lines, query])

  const linkFor = (start: number) =>
    job.bvid ? `https://www.bilibili.com/video/${job.bvid}?t=${Math.floor(start)}` : undefined

  return (
    <div className="grid gap-3">
      <label className="relative block">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="在字幕里搜关键词"
          className="min-h-10 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30"
        />
      </label>
      <ul className="grid max-h-[60vh] gap-0.5 overflow-y-auto">
        {filtered.map((line, index) => {
          const href = linkFor(line.start)
          const ts = formatDuration(line.start)
          return (
            <li
              key={index}
              className="grid grid-cols-[3.2rem_minmax(0,1fr)] items-baseline gap-2 rounded-lg px-1 py-1 hover:bg-lift/60"
            >
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  title="在 B 站跳到该时间"
                  className="tabular-nums text-xs font-medium text-brand underline-offset-2 hover:underline"
                >
                  {ts}
                </a>
              ) : (
                <span className="tabular-nums text-xs text-muted">{ts}</span>
              )}
              <span className="break-words text-sm leading-6 text-ink">{line.text}</span>
            </li>
          )
        })}
        {filtered.length === 0 && <li className="px-1 py-3 text-sm text-muted">没有匹配的字幕</li>}
      </ul>
    </div>
  )
}
