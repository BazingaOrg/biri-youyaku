import {useEffect, useState} from 'react'
import type {MouseEvent as ReactMouseEvent} from 'react'
import {Trash2, X} from 'lucide-react'
import {deleteJob, listJobs, type Job} from '../lib/api'
import {formatDate, formatDuration, formatStatus} from '../lib/format'

interface HistoryDrawerProps {
  open: boolean
  onClose: () => void
  onOpenJob: (jobId: string) => void
  onDeleted?: (jobId: string) => void
  /** 用于触发列表刷新（jobId 或状态变化时拉新数据）。 */
  refreshKey?: string | null
}

const RUNNING = new Set([
  'PENDING',
  'FETCHING_META',
  'DOWNLOADING_AUDIO',
  'TRANSCRIBING',
  'TRANSCRIPT_READY',
  'SUMMARIZING',
  'EMAILING',
])

export function HistoryDrawer({open, onClose, onOpenJob, onDeleted, refreshKey}: HistoryDrawerProps) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    let canceled = false
    setLoading(true)
    listJobs({limit: 30})
      .then((response) => { if (!canceled) setJobs(response.jobs) })
      .catch(() => { if (!canceled) setJobs([]) })
      .finally(() => { if (!canceled) setLoading(false) })
    return () => { canceled = true }
  }, [open, refreshKey])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const handleOpen = (jobId: string) => {
    onClose()
    onOpenJob(jobId)
  }

  const handleDelete = async (jobId: string, event: ReactMouseEvent) => {
    event.stopPropagation()
    try {
      await deleteJob(jobId)
      setJobs((current) => current.filter((j) => j.id !== jobId))
      onDeleted?.(jobId)
    } catch {
      // 静默：下次开抽屉会刷新
    }
  }

  return (
    <div
      className={`fixed inset-0 z-40 transition-opacity duration-[320ms] ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
        open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
      }`}
      onClick={onClose}
      aria-hidden={!open}
    >
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" />
      {/* 底部弹层：居中、最大 xl，70vh 高，圆角只在顶部 */}
      <aside
        onClick={(e) => e.stopPropagation()}
        className={`absolute inset-x-0 bottom-0 mx-auto flex h-[70vh] w-full max-w-xl flex-col rounded-t-3xl border-t border-line bg-canvas shadow-card transition-transform duration-[320ms] ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
          open ? 'translate-y-0' : 'translate-y-full'
        }`}
      >
        <div className="pt-2">
          <div className="mx-auto h-1.5 w-12 rounded-full bg-line" />
        </div>
        <header className="flex items-center justify-between gap-3 px-5 py-3">
          <h2 className="text-base font-semibold">历史</h2>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95"
          >
            <X size={18} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-3 pb-4">
          {loading && <p className="py-6 text-center text-sm text-muted">加载中</p>}
          {!loading && jobs.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">还没有任务记录</p>
          )}
          <ul className="grid gap-2">
            {jobs.map((job) => {
              const isRunning = RUNNING.has(job.status)
              return (
                <li key={job.id}>
                  <button
                    type="button"
                    onClick={() => handleOpen(job.id)}
                    className="group grid w-full grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-2xl border border-line bg-panel p-3 text-left transition hover:border-brand/30 hover:bg-brandSoft/30 active:scale-[0.99]"
                  >
                    <div className="min-w-0">
                      <p className="line-clamp-2 break-words text-sm font-medium text-ink">
                        {job.title || job.url}
                      </p>
                      <p className="mt-1 truncate text-xs text-muted">
                        {job.author || '未知 UP'} · {formatDuration(job.duration)}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        <span
                          className={`rounded-full px-2 py-0.5 ${
                            job.status === 'COMPLETED'
                              ? 'bg-brandSoft text-brand'
                              : job.status === 'FAILED'
                                ? 'bg-danger/15 text-danger'
                                : isRunning
                                  ? 'bg-warning/15 text-warning'
                                  : 'bg-lift text-muted'
                          }`}
                        >
                          {formatStatus(job.status)}
                        </span>
                        <span className="text-muted">{formatDate(job.created_at)}</span>
                      </p>
                    </div>
                    <span
                      role="button"
                      aria-label="删除"
                      onClick={(e) => void handleDelete(job.id, e)}
                      className="grid h-9 w-9 shrink-0 self-start place-items-center rounded-xl text-muted opacity-100 transition hover:bg-lift hover:text-danger active:scale-95 sm:opacity-0 sm:group-hover:opacity-100"
                    >
                      <Trash2 size={15} />
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      </aside>
    </div>
  )
}
