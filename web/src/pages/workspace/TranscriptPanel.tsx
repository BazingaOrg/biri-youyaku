import {useMemo, useState} from 'react'
import {ChevronDown, ChevronRight, Search} from 'lucide-react'
import type {Job} from '../../lib/api'
import {formatDuration} from '../../lib/format'

/**
 * 字幕原文（可折叠）。每行时间戳点击用 B 站 `?t=秒` 深链跳到视频对应时间——
 * 把总结里某段反查回原片。数据全在 job.transcript（详情接口返回）。
 */
export function TranscriptPanel({job}: {job: Job}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const lines = job.transcript ?? []

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return lines
    return lines.filter((line) => (line.text ?? '').toLowerCase().includes(q))
  }, [lines, query])

  if (lines.length === 0) return null

  const linkFor = (start: number) =>
    job.bvid ? `https://www.bilibili.com/video/${job.bvid}?t=${Math.floor(start)}` : undefined

  return (
    <section className="min-w-0 w-full rounded-3xl bg-panel p-4 shadow-card sm:p-5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <h2 className="text-lg font-semibold tracking-[-0.012em]">
          字幕原文 <span className="text-sm font-normal text-muted">· {lines.length} 段</span>
        </h2>
        {open ? (
          <ChevronDown size={18} className="shrink-0 text-muted" />
        ) : (
          <ChevronRight size={18} className="shrink-0 text-muted" />
        )}
      </button>

      {open && (
        <div className="mt-3 grid gap-3">
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

          <ul className="grid max-h-[50vh] gap-0.5 overflow-y-auto">
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
            {filtered.length === 0 && (
              <li className="px-1 py-3 text-sm text-muted">没有匹配的字幕</li>
            )}
          </ul>
        </div>
      )}
    </section>
  )
}
