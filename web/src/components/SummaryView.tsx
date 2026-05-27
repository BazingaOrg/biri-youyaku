import {Copy, Download} from 'lucide-react'
import ReactMarkdown from 'react-markdown'

interface SummaryViewProps {
  summary?: string
  title?: string
  onCopy?: () => void
  onDownload?: () => void
}

export function SummaryView({summary, title, onCopy, onDownload}: SummaryViewProps) {
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
    <section className="rounded-3xl bg-panel p-4 shadow-bili">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-[-0.012em]">总结</h2>
        <div className="flex items-center gap-2">
          <button type="button" aria-label="复制总结" onClick={copy} className="grid h-10 w-10 place-items-center rounded-full bg-lift text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-40" disabled={!summary}>
            <Copy size={17} />
          </button>
          <button type="button" aria-label="下载 Markdown" onClick={download} className="grid h-10 w-10 place-items-center rounded-full bg-lift text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-40" disabled={!summary}>
            <Download size={17} />
          </button>
        </div>
      </div>
      {summary ? (
        <div className="prose prose-sm max-w-none text-ink prose-headings:tracking-[-0.012em] prose-a:text-pink">
          <ReactMarkdown>{summary}</ReactMarkdown>
        </div>
      ) : (
        <div className="grid min-h-40 place-items-center rounded-2xl bg-lift text-sm text-muted">任务完成后会显示 Markdown 总结</div>
      )}
    </section>
  )
}
