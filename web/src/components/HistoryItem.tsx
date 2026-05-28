import {ChevronDown, ChevronRight, Trash2} from 'lucide-react'
import {useState} from 'react'
import type React from 'react'
import type {Job} from '../lib/api'
import {formatDate, formatDuration, formatStatus} from '../lib/format'

interface HistoryItemProps {
  job: Job
  onOpen: (id: string) => void
  onDelete: (id: string) => void
  /** Earlier versions of the same BV+CID (sorted newest-first, excluding the main job) */
  versions?: Job[]
  onDeleteVersion?: (id: string) => void
}

export function HistoryItem({job, onOpen, onDelete, versions, onDeleteVersion}: HistoryItemProps) {
  const [versionsOpen, setVersionsOpen] = useState(false)

  const handleDelete = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    onDelete(job.id)
  }

  return (
    <div className="rounded-2xl bg-panel shadow-card">
      {/* Main / latest job row */}
      <div className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-3 p-4 transition hover:-translate-y-0.5 hover:shadow-cardHover">
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
        <button type="button" onClick={handleDelete} aria-label="删除任务" className="grid h-10 w-10 place-items-center rounded-xl text-muted transition-[background,color,transform] hover:bg-red-50 hover:text-danger active:scale-95">
          <Trash2 size={16} />
        </button>
      </div>

      {/* Collapsible earlier versions */}
      {versions && versions.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setVersionsOpen((v) => !v)}
            className="flex min-h-9 w-full items-center gap-2 rounded-b-2xl border-t border-line/60 px-4 text-xs font-medium text-muted transition hover:bg-lift active:scale-[0.99]"
          >
            <ChevronDown size={14} className={`transition-transform ${versionsOpen ? 'rotate-180' : ''}`} />
            {versionsOpen ? '收起' : `+${versions.length} 个早期版本`}
          </button>
          {versionsOpen && (
            <div className="grid divide-y divide-line/40 rounded-b-2xl border-t border-line/60 bg-lift px-2 py-1">
              {versions.map((v) => (
                <div key={v.id} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 py-2 pl-2 pr-1">
                  <button type="button" onClick={() => onOpen(v.id)} className="min-w-0 text-left active:scale-[0.99]">
                    <span className="block truncate text-sm text-muted">
                      {formatDate(v.created_at)} · {formatStatus(v.status)}
                    </span>
                  </button>
                  <ChevronRight size={15} className="text-muted/60" />
                  <button
                    type="button"
                    onClick={(event) => { event.stopPropagation(); onDeleteVersion?.(v.id) }}
                    aria-label="删除早期版本"
                    className="grid h-8 w-8 place-items-center rounded-xl text-muted/60 transition hover:bg-red-50 hover:text-danger active:scale-95"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
