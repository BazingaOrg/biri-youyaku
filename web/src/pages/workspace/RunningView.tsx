import {useMemo} from 'react'
import {Copy, History, Plus, RotateCw, XCircle} from 'lucide-react'
import type {Job} from '../../lib/api'
import {isRunning} from '../../lib/jobStatus'
import {friendlyError} from '../../lib/errorMap'
import {IconButton} from '../../components/IconButton'
import {StepCarousel} from '../../components/StepCarousel'
import {useToast} from '../../components/ToastProvider'
import {MetaBar} from './MetaBar'
import {buildSteps, statusToStepIndex} from './steps'

interface RunningViewProps {
  job: Job
  onCancel: () => void
  onRetry: () => void
  onNew: () => void
  onOpenHistory: () => void
  busy: boolean
  cancelPending: boolean
}

export function RunningView({
  job,
  onCancel,
  onRetry,
  onNew,
  onOpenHistory,
  busy,
  cancelPending,
}: RunningViewProps) {
  const steps = useMemo(() => buildSteps(job), [job])
  const currentIdx = statusToStepIndex(job.status)
  const failure = job.error_message ? friendlyError(job.error_code, job.error_message, job.error_stage) : null
  const canCancel = isRunning(job.status)
  const canRetry = job.status === 'FAILED'
  const toast = useToast()

  const copyErrorDetail = async () => {
    if (!failure) return
    const detail = [
      `Job ID: ${job.id}`,
      `Stage: ${job.error_stage || '-'}`,
      `Error code: ${job.error_code || '-'}`,
      `Message: ${job.error_message || '-'}`,
    ].join('\n')
    const taskName = job.title || undefined
    try {
      await navigator.clipboard.writeText(detail)
      toast.success('错误详情已复制', undefined, {taskName})
    } catch {
      toast.error('复制失败', '请手动选中复制', {taskName})
    }
  }

  return (
    <div className="grid min-w-0 gap-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <IconButton icon={<Plus size={18} />} label="新建" onClick={onNew} />
        <IconButton icon={<History size={18} />} label="历史" onClick={onOpenHistory} />
      </div>
      <MetaBar job={job} />
      <StepCarousel steps={steps} currentIndex={currentIdx} />
      {failure && (
        <div className="rounded-2xl border border-danger/50 bg-danger/20 p-4 text-sm text-danger shadow-card">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-base font-semibold">{failure.title}</p>
            <button
              type="button"
              aria-label="复制错误详情"
              onClick={copyErrorDetail}
              className="inline-flex items-center gap-1 rounded-xl border border-danger/40 bg-panel/40 px-2 py-1 text-xs text-danger transition hover:bg-danger/30"
            >
              <Copy size={12} /> 复制
            </button>
          </div>
          <p className="mt-1.5 break-words leading-6 text-danger/90">{failure.message}</p>
        </div>
      )}
      {(canCancel || canRetry) && (
        <div className="flex flex-wrap items-center justify-center gap-2">
          {canCancel && (
            <IconButton
              icon={cancelPending ? <RotateCw size={18} className="animate-spin" /> : <XCircle size={18} />}
              label={cancelPending ? '取消中…' : '取消'}
              onClick={onCancel}
              disabled={cancelPending}
              variant="danger"
            />
          )}
          {canRetry && (
            <IconButton
              icon={<RotateCw size={18} />}
              label={failure?.actionLabel || '重试'}
              onClick={onRetry}
              disabled={busy}
              variant="primary"
            />
          )}
        </div>
      )}
    </div>
  )
}
