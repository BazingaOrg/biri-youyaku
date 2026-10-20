import {useMemo, useState} from 'react'
import ReactMarkdown from 'react-markdown'
import {Copy, Search} from 'lucide-react'
import type {Job} from '../../lib/api'
import {formatDuration} from '../../lib/format'
import {transcriptToPlainText} from '../../lib/subtitle'
import {PROSE} from '../../lib/prose'
import {useToast} from '../../components/ToastProvider'

type Tab = 'notes' | 'transcript'

export function SummaryTabs({job}: {job: Job}) {
  const summary = job.summary ?? ''
  const hasTranscript = (job.transcript?.length ?? 0) > 0
  const [tab, setTab] = useState<Tab>('notes')
  const toast = useToast()

  const tabs: Array<[Tab, string]> = [['notes', '笔记']]
  if (hasTranscript) tabs.push(['transcript', '字幕'])
  const copyLabel = tab === 'notes' ? '复制笔记' : '复制字幕'
  const copyText = tab === 'notes' ? summary : transcriptToPlainText(job.transcript ?? [])

  const copyCurrent = async () => {
    const text = copyText.trim()
    if (!text) return
    const taskName = job.title || undefined
    try {
      await navigator.clipboard.writeText(copyText)
      toast.success(tab === 'notes' ? '笔记已复制' : '字幕已复制', undefined, {taskName})
    } catch {
      toast.error('复制失败', '请手动选中复制', {taskName})
    }
  }

  return (
    <section className="min-w-0 w-full rounded-2xl bg-lift/70 p-4 sm:p-5">
      <div className="mb-4 flex min-w-0 items-center gap-2">
        <div className="inline-flex min-w-0 gap-1 rounded-2xl bg-lift p-1 text-sm">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`min-h-9 rounded-xl px-4 transition-[background-color,color] ${
                tab === key ? 'bg-brandSolid text-onBrand' : 'text-muted hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => void copyCurrent()}
          disabled={!copyText.trim()}
          aria-label={copyLabel}
          className="ml-auto inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-xl px-2.5 text-sm text-muted transition-[transform,background-color,color] duration-150 ease-out hover:bg-lift hover:text-ink active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Copy size={15} />
          {copyLabel}
        </button>
      </div>

      <div key={tab}>
        {tab === 'notes' &&
          (summary ? <NotesView markdown={summary} /> : <p className="text-sm text-muted">没有笔记内容</p>)}
        {tab === 'transcript' && hasTranscript && <TranscriptList job={job} />}
      </div>
    </section>
  )
}

function NotesView({markdown}: {markdown: string}) {
  return (
    <div className={`min-w-0 ${PROSE}`}>
      <ReactMarkdown>{markdown}</ReactMarkdown>
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
