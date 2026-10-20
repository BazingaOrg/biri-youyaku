import {useState} from 'react'
import {History, Plus, RotateCw} from 'lucide-react'
import {resendEmail, type Job} from '../../lib/api'
import {useToast} from '../../components/ToastProvider'
import {MetaBar} from './MetaBar'
import {SummaryTabs} from './SummaryTabs'

interface DoneViewProps {
  job: Job
  onNew: () => void
  onOpenHistory: () => void
  onResummarize: () => void
  resummarizeBusy?: boolean
}

export function DoneView({
  job,
  onNew,
  onOpenHistory,
  onResummarize,
  resummarizeBusy = false,
}: DoneViewProps) {
  const [resending, setResending] = useState(false)
  const toast = useToast()
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
          onClick={onResummarize}
          disabled={resummarizeBusy || !job.transcript?.length}
          className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-lift px-3.5 text-sm text-muted transition-[transform,background-color,color] duration-150 ease-out hover:bg-line/70 hover:text-ink active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RotateCw size={16} />
          {resummarizeBusy ? '重新总结中…' : '重新总结'}
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
