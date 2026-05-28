import {Copy, Download, Mail} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import type {Job} from '../lib/api'
import {formatDuration} from '../lib/format'

interface SummaryViewProps {
  summary?: string
  title?: string
  job?: Job
  onCopy?: () => void
  onDownload?: () => void
  onEmail?: () => void
}

function summarizeDuration(job?: Job) {
  const summarizeTiming = job?.stage_timings?.find((timing) => timing.stage === 'SUMMARIZING')
  if (!summarizeTiming) {
    return null
  }
  return Math.round(summarizeTiming.duration_ms / 1000)
}

export function SummaryView({summary, title, job, onCopy, onDownload, onEmail}: SummaryViewProps) {
  const copy = async () => {
    if (summary) {
      await navigator.clipboard.writeText(summary)
      onCopy?.()
    }
  }

  const download = () => {
    if (!summary) {
      return
    }
    const blob = new Blob([summary], {type: 'text/markdown;charset=utf-8'})
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${title || 'summary'}.md`
    anchor.click()
    URL.revokeObjectURL(url)
    onDownload?.()
  }

  return (
    <section className="rounded-3xl bg-panel p-4 shadow-card">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-[-0.012em]">总结</h2>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={copy} className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-lift px-3 text-sm text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-40" disabled={!summary}>
            <Copy size={17} />
            复制 Markdown
          </button>
          <button type="button" onClick={download} className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-lift px-3 text-sm text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-40" disabled={!summary}>
            <Download size={17} />
            下载 .md
          </button>
          {onEmail && (
            <button type="button" onClick={onEmail} className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-lift px-3 text-sm text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-40" disabled={!summary}>
              <Mail size={17} />
              发送邮件
            </button>
          )}
        </div>
      </div>
      {summary ? (
        <>
          <div className="mb-4 grid grid-cols-2 gap-2 text-xs text-muted sm:grid-cols-4">
            <div className="rounded-2xl bg-lift p-3">
              <span className="block">字数</span>
              <strong className="mt-1 block text-sm text-ink">{summary.length}</strong>
            </div>
            <div className="rounded-2xl bg-lift p-3">
              <span className="block">模型</span>
              <strong className="mt-1 block truncate text-sm text-ink">{job?.options.llm_model || '-'}</strong>
            </div>
            <div className="rounded-2xl bg-lift p-3">
              <span className="block">耗时</span>
              <strong className="mt-1 block text-sm text-ink">{summarizeDuration(job) == null ? '-' : formatDuration(summarizeDuration(job) || 0)}</strong>
            </div>
            <div className="rounded-2xl bg-lift p-3">
              <span className="block">Token</span>
              <strong className="mt-1 block text-sm text-ink">{String(job?.token_usage?.total_tokens ?? '-')}</strong>
            </div>
          </div>
          <div className="prose prose-sm max-w-none text-ink prose-headings:tracking-[-0.012em] prose-a:text-brand">
            <ReactMarkdown>{summary}</ReactMarkdown>
          </div>
        </>
      ) : (
        <div className="grid min-h-40 place-items-center rounded-2xl bg-lift text-sm text-muted">任务完成后会显示 Markdown 总结</div>
      )}
    </section>
  )
}
