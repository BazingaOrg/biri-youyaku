import {Download, ListTree} from 'lucide-react'
import {useState} from 'react'
import type React from 'react'
import type {Job} from '../lib/api'
import {formatDuration} from '../lib/format'
import {parseTranscriptFile} from '../lib/transcript'

interface TranscriptViewProps {
  job: Job
  onUpload?: (items: Job['transcript']) => void
}

export function TranscriptView({job, onUpload}: TranscriptViewProps) {
  const [expanded, setExpanded] = useState(false)
  const [dragging, setDragging] = useState(false)
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
  const upload = async (file: File) => {
    const textContent = await file.text()
    onUpload?.(parseTranscriptFile(textContent))
  }
  const handleDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (!file) {
      return
    }
    void upload(file)
  }

  return (
    <section
      onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`rounded-3xl bg-panel p-4 shadow-card transition ${dragging ? 'ring-2 ring-brand' : ''}`}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <button type="button" onClick={() => setExpanded((value) => !value)} className="flex min-h-10 items-center gap-2 rounded-xl pr-3 text-left text-lg font-semibold tracking-[-0.012em] transition active:scale-95">
          <ListTree size={18} />
          字幕
          <span className="text-sm font-normal text-muted">{expanded ? '收起' : '展开'}</span>
        </button>
        <div className="flex items-center gap-3 text-sm text-muted">
          <span className="rounded-full bg-brandSoft px-3 py-1 font-medium text-brand">{sourceLabel}</span>
          <span>{items.length} 行</span>
          <button type="button" onClick={download} disabled={items.length === 0} className="inline-flex min-h-9 items-center gap-2 rounded-full bg-lift px-3 text-muted transition-[background,transform,opacity] hover:bg-line/70 active:scale-95 disabled:opacity-40">
            <Download size={15} />
            下载字幕
          </button>
        </div>
      </div>
      {expanded ? (
        <div className="max-h-[520px] overflow-y-auto rounded-2xl bg-lift p-2">
          {items.length > 0 ? items.map((item, index) => (
            <button key={`${item.start}-${index}`} type="button" onClick={() => navigator.clipboard.writeText(item.text)} className="grid w-full grid-cols-[5.5rem_1fr] gap-3 rounded-xl px-3 py-2 text-left text-sm leading-6 transition hover:bg-panel active:scale-[0.99]">
              <span className="font-mono text-xs text-muted">{formatDuration(item.start)}</span>
              <span className="text-ink">{item.text}</span>
            </button>
          )) : (
            <div className="grid min-h-24 place-items-center text-sm text-muted">字幕还未就绪</div>
          )}
        </div>
      ) : (
        <div className="rounded-2xl bg-lift p-4 text-sm leading-6 text-muted">
          {text ? `${text.slice(0, 180)}${text.length > 180 ? '...' : ''}` : '字幕还未就绪'}
        </div>
      )}
      {onUpload && (
        <label className="mt-3 flex min-h-11 cursor-pointer items-center justify-center rounded-2xl border border-dashed border-line px-3 text-sm text-muted transition hover:border-brand hover:text-brand active:scale-[0.99]">
          拖入或选择 .txt / .srt / .vtt 字幕覆盖当前字幕
          <input type="file" accept=".txt,.srt,.vtt,text/plain" className="hidden" onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) {
              void upload(file)
            }
            event.currentTarget.value = ''
          }} />
        </label>
      )}
    </section>
  )
}
