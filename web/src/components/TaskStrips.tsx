import {Link} from 'wouter'
import type {Job} from '../lib/api'
import {formatStatus} from '../lib/format'

export function TaskStrips({running, failed}: {running: Job[]; failed: Job[]}) {
  if (running.length === 0 && failed.length === 0) return null
  return (
    <div className="mt-4 grid gap-2">
      {running.slice(0, 3).map((job) => (
        <div
          key={job.id}
          className="flex flex-wrap items-center gap-3 rounded-[14px] bg-brandSoft px-3.5 py-2.5 text-sm"
        >
          <span className="h-2 w-2 shrink-0 rounded-full bg-brand motion-safe:animate-pulse" />
          <span className="min-w-0 flex-1 basis-[220px] break-words">
            正在生成 <b className="font-semibold">{job.title || '未命名视频'}</b>
            {job.status ? ` · ${formatStatus(job.status)}` : ''}
          </span>
          <Link href={`/jobs/${job.id}`} className="shrink-0 font-medium whitespace-nowrap text-brand">
            查看进度
          </Link>
        </div>
      ))}
      {failed.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-[14px] bg-warning/15 px-3.5 py-2.5 text-sm">
          <span className="h-2 w-2 shrink-0 rounded-full bg-warning" />
          <span className="min-w-0 flex-1 basis-[220px] break-words">
            {failed.length} 个任务没有完成：<b className="font-semibold">{failed[0].title || '未命名视频'}</b>
          </span>
          <Link href={`/jobs/${failed[0].id}`} className="shrink-0 font-medium whitespace-nowrap text-warning">
            处理
          </Link>
        </div>
      ) : null}
    </div>
  )
}
