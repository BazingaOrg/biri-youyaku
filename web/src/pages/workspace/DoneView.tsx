import {type ReactNode, useRef, useState} from 'react'
import {Captions, Copy, FileDown, History, MoreHorizontal, Music, Plus, RotateCw} from 'lucide-react'
import {resendEmail, type Job} from '../../lib/api'
import {useToast} from '../../components/ToastProvider'
import {MetaBar} from './MetaBar'
import {SummaryTabs} from './SummaryTabs'

interface DoneViewProps {
  job: Job
  onNew: () => void
  onOpenHistory: () => void
  onDownloadAudio: () => void
  onCopy: () => void
  onDownloadMarkdown: () => void
  onDownloadSubtitle: () => void
  onResummarize: () => void
  resummarizeBusy?: boolean
}

interface MoreActionProps {
  icon: ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
}

function MoreAction({icon, label, onClick, disabled}: MoreActionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex min-h-10 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm text-muted transition-colors hover:bg-lift hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
    >
      {icon}
      {label}
    </button>
  )
}

export function DoneView({
  job,
  onNew,
  onOpenHistory,
  onDownloadAudio,
  onCopy,
  onDownloadMarkdown,
  onDownloadSubtitle,
  onResummarize,
  resummarizeBusy = false,
}: DoneViewProps) {
  const [resending, setResending] = useState(false)
  const moreRef = useRef<HTMLDetailsElement>(null)
  const toast = useToast()
  const runMoreAction = (action: () => void) => {
    action()
    if (moreRef.current) moreRef.current.open = false
  }
  const resend = async () => {
    setResending(true)
    try {
      await resendEmail(job.id)
      toast.success('已重发邮件', undefined, {taskName: job.title || undefined})
    } catch (err) {
      toast.error('重发失败', err instanceof Error ? err.message : '请重试', {taskName: job.title || undefined})
    } finally {
      setResending(false)
    }
  }
  return (
    <div className="grid min-w-0 gap-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <button
          type="button"
          onClick={onCopy}
          disabled={!job.summary}
          className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-brandSolid px-3.5 text-sm font-medium text-onBrand shadow-card transition-[transform,filter] duration-150 ease-out hover:brightness-105 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Copy size={16} />
          复制总结全文
        </button>
        <button
          type="button"
          onClick={onNew}
          className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-lift px-3.5 text-sm text-muted transition-[transform,background-color,color] duration-150 ease-out hover:bg-line/70 hover:text-ink active:scale-[0.97]"
        >
          <Plus size={16} />
          新建
        </button>
        <button
          type="button"
          onClick={onOpenHistory}
          className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-lift px-3.5 text-sm text-muted transition-[transform,background-color,color] duration-150 ease-out hover:bg-line/70 hover:text-ink active:scale-[0.97]"
        >
          <History size={16} />
          历史
        </button>
        <details ref={moreRef} className="group/more relative">
          <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-xl bg-lift px-3.5 text-sm text-muted transition-[transform,background-color,color] duration-150 ease-out hover:bg-line/70 hover:text-ink active:scale-[0.97] [&::-webkit-details-marker]:hidden">
            <MoreHorizontal size={16} />
            更多
          </summary>
          <div className="absolute right-0 top-full z-20 mt-2 grid w-48 gap-1 rounded-2xl border border-line/70 bg-panel/95 p-1.5 shadow-card backdrop-blur">
            <MoreAction
              icon={<RotateCw size={16} />}
              label={resummarizeBusy ? '重新总结中…' : '重新总结'}
              onClick={() => runMoreAction(onResummarize)}
              disabled={resummarizeBusy || !job.transcript?.length}
            />
            <MoreAction
              icon={<FileDown size={16} />}
              label="下载 Markdown"
              onClick={() => runMoreAction(onDownloadMarkdown)}
              disabled={!job.summary}
            />
            <MoreAction
              icon={<Captions size={16} />}
              label="下载字幕"
              onClick={() => runMoreAction(onDownloadSubtitle)}
              disabled={!job.transcript?.length}
            />
            <MoreAction
              icon={<Music size={16} />}
              label="下载音频"
              onClick={() => runMoreAction(onDownloadAudio)}
              disabled={!job.audio_available}
            />
          </div>
        </details>
      </div>
      <MetaBar job={job} />
      {job.email_error && (
        <p className="px-1 text-xs text-warning">
          邮件未送达（{job.email_error}）
          {' · '}
          <button
            type="button"
            onClick={() => void resend()}
            disabled={resending}
            className="underline underline-offset-2 transition hover:text-warning/80 disabled:opacity-50"
          >
            {resending ? '重发中…' : '重发'}
          </button>
        </p>
      )}
      <SummaryTabs job={job} />
    </div>
  )
}
