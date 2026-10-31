import {Check, RotateCw} from 'lucide-react'
import {Link} from 'wouter'
import {Button, buttonClassName} from '../../components/Button'
import {ClampText} from '../../components/ClampText'
import {type JobStatus, type UpVideo} from '../../lib/api'
import {formatDay, formatDuration} from '../../lib/format'
import {isRunning} from '../../lib/jobStatus'
import {docHref} from '../../lib/docNav'

export function VideoRow({
  video,
  status,
  jobId,
  busy,
  onSummarize,
  index = 0,
}: {
  video: UpVideo
  status: JobStatus | null
  jobId: string | null
  busy: boolean
  onSummarize: () => void
  index?: number
}) {
  const done = status === 'COMPLETED'
  const running = status != null && isRunning(status)
  const failed = status === 'FAILED' || status === 'CANCELED'
  const readId = video.document_id || jobId

  return (
    <li
      style={{animationDelay: `${Math.min(index, 6) * 40}ms`}}
      className="grid grid-cols-[7.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl bg-lift/55 p-2 transition-[background-color] hover:bg-brandSoft/30"
    >
      <div className="relative aspect-video overflow-hidden rounded-xl bg-panel">
        {video.cover && (
          <img
            src={video.cover}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = 'none'
            }}
          />
        )}
        <span className="absolute bottom-1 right-1 rounded bg-ink/70 px-1 text-[10px] font-medium text-canvas">
          {formatDuration(video.duration)}
        </span>
      </div>

      <div className="min-w-0">
        <ClampText
          href={video.url}
          external
          text={video.title}
          className="text-sm font-medium text-ink hover:text-brand"
        />
        <p className="mt-1 truncate text-xs text-muted">{formatDay(video.pubdate * 1000)}</p>
      </div>

      <div className="flex items-center justify-end">
        {done && readId ? (
          <Link
            href={docHref(readId, {from: 'up'})}
            className={buttonClassName({variant: 'secondary', size: 'sm', className: 'text-brand'})}
          >
            <Check size={14} />
            阅读笔记
          </Link>
        ) : done ? (
          <span className="px-2 text-xs text-muted">已完成</span>
        ) : running && jobId ? (
          <Link
            href={`/jobs/${jobId}`}
            className={buttonClassName({variant: 'secondary', size: 'sm', className: 'text-warning'})}
          >
            <RotateCw size={13} className="animate-spin" />
            进行中
          </Link>
        ) : (
          <Button
            size="sm"
            variant="primary"
            onClick={onSummarize}
            disabled={busy}
            title={failed ? '上次未完成，重新总结' : undefined}
          >
            {busy ? <RotateCw size={13} className="animate-spin" /> : null}
            {failed ? '重试' : '总结'}
          </Button>
        )}
      </div>
    </li>
  )
}
