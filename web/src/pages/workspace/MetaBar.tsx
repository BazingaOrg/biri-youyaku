import {ExternalLink} from 'lucide-react'
import type {Job} from '../../lib/api'
import {formatDuration} from '../../lib/format'
import {AuthorLink} from '../../components/AuthorLink'
import {ClampText} from '../../components/ClampText'

export function MetaBar({job}: {job: Job}) {
  return (
    <div className="grid min-w-0 w-full gap-2 rounded-2xl bg-lift px-4 py-3 sm:px-5 sm:py-4">
      <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted">
        <span>{formatDuration(job.duration)}</span>
        <a
          href={job.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-muted hover:text-ink"
        >
          视频源 <ExternalLink size={12} />
        </a>
      </div>
      <ClampText text={job.title || '识别中…'} className="text-base font-semibold leading-snug text-ink" />
      <AuthorLink job={job} variant="chip" />
    </div>
  )
}
