import {useState} from 'react'
import {Link} from 'wouter'
import {Plus, RotateCw} from 'lucide-react'
import {resendEmail, type Job} from '../../lib/api'
import {useToast} from '../../components/ToastProvider'
import {Button, buttonClassName} from '../../components/Button'
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
  const readHref = job.document_id
    ? `/doc/${job.document_id}?from=task`
    : job.bvid
      ? `/search?q=${encodeURIComponent(job.bvid)}&scope=all`
      : '/'
  return (
    <div className="grid min-w-0 gap-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Link href={readHref} className={buttonClassName({variant: 'primary', size: 'md'})}>
          阅读笔记
        </Link>
        <Button
          variant="secondary"
          onClick={onResummarize}
          disabled={resummarizeBusy || !job.transcript?.length}
        >
          <RotateCw size={16} />
          {resummarizeBusy ? '重新生成中…' : '重新生成笔记'}
        </Button>
        <Button variant="ghost" onClick={onNew}>
          <Plus size={16} />
          新建笔记
        </Button>
        <Button variant="ghost" onClick={onOpenHistory}>
          任务
        </Button>
      </div>
      {!job.summary && !job.document_id ? (
        <p className="px-1 text-center text-sm text-muted">这篇笔记已经永久删除，任务记录还在。</p>
      ) : null}
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
