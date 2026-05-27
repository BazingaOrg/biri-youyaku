import {Download, ListTree} from 'lucide-react'
import type {Job} from '../lib/api'
import {formatDuration} from '../lib/format'

interface TranscriptViewProps {
  job: Job
}

export function TranscriptView({job}: TranscriptViewProps) {
  const items = job.transcript ?? []
  const text = items.map((item) => item.text).join('\n')
  const filename = (job.title || job.bvid || job.id || 'transcript').replace(/[\\/:*?"<>|]+/g, '_')
  const download = () => {
    const blob = new Blob([
      items
        .map((item) => `[${formatDuration(item.start)} - ${formatDuration(item.end)}] ${item.text}`)
        .join('\n'),
    ], {type: 'text/plain;charset=utf-8'})
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${filename}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const sourceLabel = job.subtitle_source === 'platform' ? '官方字幕' : job.subtitle_source === 'asr' ? 'ASR 识别' : '未知来源'

  return (
    <section className="rounded-3xl bg-panel p-4 shadow-bili">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-[-0.012em]">
          <ListTree size={18} />
          字幕
        </h2>
        <div className="flex items-center gap-3 text-sm text-muted">
          <span className="rounded-full bg-pink/10 px-3 py-1 font-medium text-pink">{sourceLabel}</span>
          <button type="button" onClick={download} disabled={items.length === 0} className="inline-flex min-h-9 items-center gap-2 rounded-full bg-lift px-3 text-muted transition-[background,transform,opacity] hover:bg-line/70 active:scale-95 disabled:opacity-40">
            <Download size={15} />
            下载字幕
          </button>
        </div>
      </div>
      <pre className="max-h-[520px] overflow-y-auto whitespace-pre-wrap break-words rounded-2xl bg-lift p-3 text-sm leading-6 text-ink">
        {text || '字幕还未就绪'}
      </pre>
    </section>
  )
}
