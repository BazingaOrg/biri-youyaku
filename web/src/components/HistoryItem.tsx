import {ChevronRight, Trash2} from 'lucide-react'
import type React from 'react'
import type {Job} from '../lib/api'
import {formatDate, formatDuration, formatStatus} from '../lib/format'

interface HistoryItemProps {
  job: Job
  onOpen: (id: string) => void
  onDelete: (id: string) => void
}

export function HistoryItem({job, onOpen, onDelete}: HistoryItemProps) {
  const handleDelete = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    onDelete(job.id)
  }

  return (
    <div className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-3 rounded-3xl bg-panel p-4 shadow-bili transition hover:-translate-y-0.5 hover:shadow-biliHover">
      <button type="button" onClick={() => onOpen(job.id)} className="min-w-0 text-left transition-transform active:scale-[0.99]">
        <span className="block truncate font-medium">{job.title || job.url}</span>
        <span className="mt-1 block text-sm text-muted">
          {job.author || '未知 UP'} · {formatDuration(job.duration)} · {formatDate(job.created_at)}
        </span>
      </button>
      <span className="flex items-center gap-2 text-sm text-muted">
        {formatStatus(job.status)}
        <ChevronRight size={17} />
      </span>
      <button type="button" onClick={handleDelete} aria-label="删除任务" className="grid h-9 w-9 place-items-center rounded-full text-muted transition-[background,color,transform] hover:bg-pink/10 hover:text-pink active:scale-95">
        <Trash2 size={16} />
      </button>
    </div>
  )
}
