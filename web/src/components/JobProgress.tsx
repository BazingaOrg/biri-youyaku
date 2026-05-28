import {Check, Circle, Loader2, X} from 'lucide-react'
import type {JobStatus} from '../lib/api'
import {formatStatus} from '../lib/format'

const fullSteps: JobStatus[] = [
  'FETCHING_META',
  'DOWNLOADING_AUDIO',
  'TRANSCRIBING',
  'TRANSCRIPT_READY',
  'SUMMARIZING',
  'COMPLETED',
]

// When the platform subtitle was used, the download + transcribe stages are
// skipped entirely, so we collapse them into the timeline.
const platformSteps: JobStatus[] = [
  'FETCHING_META',
  'TRANSCRIPT_READY',
  'SUMMARIZING',
  'COMPLETED',
]

export function JobProgress({status, emailEnabled = false, subtitleSource, downloadPercent}: {
  status: JobStatus
  emailEnabled?: boolean
  /** 'platform' | 'asr' | null/undefined — drives whether download/transcribe are shown */
  subtitleSource?: string | null
  downloadPercent?: number | null
}) {
  // Use shorter timeline once we know the job used a platform subtitle.
  // While subtitle source is still unknown keep the full list so the user sees expected steps.
  const baseSteps = subtitleSource === 'platform' ? platformSteps : fullSteps
  const visibleSteps = emailEnabled
    ? [...baseSteps.slice(0, -1), 'EMAILING' as JobStatus, 'COMPLETED' as JobStatus]
    : baseSteps
  const currentIndex = visibleSteps.indexOf(status)
  const failed = status === 'FAILED' || status === 'CANCELED'

  return (
    <section className="rounded-3xl bg-panel p-4 shadow-card">
      <div className="mb-4 flex items-center justify-between gap-3">
        <span className="text-sm text-muted">状态</span>
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${failed ? 'bg-red-50 text-danger' : status === 'TRANSCRIPT_READY' ? 'bg-amber-50 text-warning' : 'bg-brandSoft text-brand'}`}>
          {formatStatus(status)}
        </span>
      </div>
      {status === 'DOWNLOADING_AUDIO' && downloadPercent != null && (
        <div className="mb-4">
          <div className="mb-1 flex items-center justify-between text-xs text-muted">
            <span>下载进度</span>
            <span>{Math.round(downloadPercent)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-lift">
            <div className="h-full rounded-full bg-brand transition-[width]" style={{width: `${Math.round(downloadPercent)}%`}} />
          </div>
        </div>
      )}
      <div className="space-y-3">
        {visibleSteps.map((step, index) => {
          const done = status === 'COMPLETED' || (currentIndex > index && currentIndex >= 0)
          const active = status === step
          return (
            <div key={step} className="flex min-h-8 items-center gap-3">
              <span className={`grid h-7 w-7 place-items-center rounded-full ${done ? 'bg-brand text-white' : active ? 'bg-brandSoft text-brand' : 'bg-lift text-muted'}`}>
                {done ? <Check size={15} /> : active ? <Loader2 size={15} className="animate-spin" /> : failed ? <X size={15} /> : <Circle size={13} />}
              </span>
              <span className={active ? 'font-medium text-ink' : 'text-muted'}>{formatStatus(step)}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
