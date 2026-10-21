import {Check, RotateCw} from 'lucide-react'
import {Link} from 'wouter'
import {Button, buttonClassName} from '../../components/Button'
import {type JobStatus, type UpVideo} from '../../lib/api'
import {formatDay, formatDuration} from '../../lib/format'
import {isRunning} from '../../lib/jobStatus'

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
        <a
          href={video.url}
          target="_blank"
          rel="noreferrer"
          className="line-clamp-2 break-words text-sm font-medium text-ink hover:text-brand"
        >
          {video.title}
        </a>
        <p className="mt-1 truncate text-xs text-muted">{formatDay(video.pubdate * 1000)}</p>
      </div>

      <div className="flex items-center justify-end">
        {done ? (
          <Link
            href={`/jobs/${jobId}`}
            className={buttonClassName({variant: 'secondary', size: 'sm', className: 'text-brand'})}
          >
            <Check size={14} />
            查看
          </Link>
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
