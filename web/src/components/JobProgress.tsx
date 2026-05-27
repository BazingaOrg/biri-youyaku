import {Check, Circle, Loader2, X} from 'lucide-react'
import type {JobStatus} from '../lib/api'
import {formatStatus} from '../lib/format'

const steps: JobStatus[] = [
  'FETCHING_META',
  'DOWNLOADING_AUDIO',
  'TRANSCRIBING',
  'TRANSCRIPT_READY',
  'SUMMARIZING',
  'EMAILING',
  'COMPLETED',
]

export function JobProgress({status}: {status: JobStatus}) {
  const currentIndex = steps.indexOf(status)
  const failed = status === 'FAILED' || status === 'CANCELED'

  return (
    <section className="rounded-3xl bg-panel p-4 shadow-bili">
      <div className="mb-4 flex items-center justify-between gap-3">
        <span className="text-sm text-muted">状态</span>
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${failed ? 'bg-red-50 text-danger' : 'bg-accentSoft text-accent'}`}>
          {formatStatus(status)}
        </span>
      </div>
      <div className="space-y-3">
        {steps.map((step, index) => {
          const done = status === 'COMPLETED' || (currentIndex > index && currentIndex >= 0)
          const active = status === step
          return (
            <div key={step} className="flex min-h-8 items-center gap-3">
              <span className={`grid h-7 w-7 place-items-center rounded-full ${done ? 'bg-accent text-white' : active ? 'bg-accentSoft text-accent' : 'bg-lift text-muted'}`}>
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
