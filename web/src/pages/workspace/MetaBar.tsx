import {ExternalLink} from 'lucide-react'
import type {Job} from '../../lib/api'
import {formatDuration} from '../../lib/format'
import {AuthorLink} from '../../components/AuthorLink'
import {ClampText} from '../../components/ClampText'
import {playbackUrl, sourceLabel} from '../../lib/sourceUrl'

export function MetaBar({job}: {job: Job}) {
  const sourceUrl = playbackUrl(job.url, job.provider)
  const label = sourceLabel(job.provider) || '原页面'
  return (
    <div className="grid min-w-0 w-full gap-2 rounded-2xl bg-lift px-4 py-3 sm:px-5 sm:py-4">
      <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted">
        <span>{formatDuration(job.duration)}</span>
        {sourceUrl ? <a
          href={sourceUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-muted hover:text-ink"
        >
          {label} <ExternalLink size={12} />
        </a> : null}
      </div>
      <ClampText text={job.title || '识别中…'} className="text-base font-semibold leading-snug text-ink" />
      <AuthorLink job={job} variant="chip" />
    </div>
  )
}
