import {ExternalLink} from 'lucide-react'
import type {Job} from '../../lib/api'
import {formatDuration} from '../../lib/format'

/** 顶部固定的视频元信息条：BV / 字幕来源 / 时长 / 视频源链接 / 标题 / UP。 */
export function MetaBar({job}: {job: Job}) {
  return (
    <div className="grid min-w-0 w-full gap-2 rounded-2xl bg-lift px-4 py-3 sm:px-5 sm:py-4">
      <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted">
        <span className="rounded-full bg-brandSoft px-2.5 py-1 text-brand">{job.bvid || '识别中'}</span>
        <span>
          {job.subtitle_source === 'platform'
            ? '官方字幕'
            : job.subtitle_source === 'asr'
              ? '语音转写'
              : '字幕未定'}
        </span>
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
      <p className="line-clamp-2 break-words text-base font-semibold leading-snug text-ink">
        {job.title || '识别中…'}
      </p>
      <p className="truncate text-xs text-muted">{job.author || '未知 UP'}</p>
    </div>
  )
}
