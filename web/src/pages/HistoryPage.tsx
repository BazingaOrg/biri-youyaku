import {useCallback, useEffect, useState} from 'react'
import {ArrowLeft, Trash2} from 'lucide-react'
import type {Job} from '../lib/api'
import {deleteAllJobs, deleteJob, listJobs} from '../lib/api'
import {HistoryItem} from '../components/HistoryItem'
import {ConfirmDialog} from '../components/ConfirmDialog'
import {useToast} from '../components/ToastProvider'

interface HistoryPageProps {
  onOpen: (jobId: string) => void
  onHome?: () => void
}

export function HistoryPage({onOpen, onHome}: HistoryPageProps) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<{type: 'one' | 'all'; job?: Job} | null>(null)
  const [deleting, setDeleting] = useState(false)
  const toast = useToast()

  const reload = useCallback(() => {
    listJobs()
      .then((response) => {
        setJobs(response.jobs)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : '加载历史失败'))
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const handleDelete = async () => {
    if (!confirm) {
      return
    }
    setDeleting(true)
    try {
      if (confirm.type === 'all') {
        const response = await deleteAllJobs()
        toast.success('历史已清理', `已删除 ${response.deleted_count} 个任务，保留 ${response.skipped_count} 个进行中任务。`, {autoClose: true})
      } else if (confirm.job) {
        await deleteJob(confirm.job.id)
        toast.success('任务已删除', confirm.job.title || confirm.job.url, {autoClose: true})
      }
      setConfirm(null)
      reload()
    } catch (err) {
      const message = err instanceof Error ? err.message : '删除任务失败'
      setError(message)
      toast.error('删除失败', message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="grid gap-4">
      <div>
        {onHome && (
          <button type="button" onClick={onHome} className="mb-3 inline-flex min-h-10 items-center gap-2 rounded-lg px-1 text-muted transition-transform active:scale-95">
            <ArrowLeft size={18} />
            返回首页
          </button>
        )}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold">历史任务</h1>
            <p className="mt-2 text-sm text-muted">按创建时间倒序排列，点击任一任务查看总结和状态。</p>
          </div>
          <button
            type="button"
            onClick={() => setConfirm({type: 'all'})}
            disabled={jobs.length === 0}
            className="inline-flex min-h-10 items-center gap-2 rounded-full bg-pink px-4 text-sm font-semibold text-white shadow-bili transition hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Trash2 size={16} />
            清除全部
          </button>
        </div>
      </div>
      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-danger">{error}</p>}
      <div className="grid gap-3">
        {jobs.map((job) => <HistoryItem key={job.id} job={job} onOpen={onOpen} onDelete={() => setConfirm({type: 'one', job})} />)}
        {jobs.length === 0 && !error && (
          <div className="rounded-3xl bg-panel p-8 text-center text-muted shadow-bili">暂无历史任务</div>
        )}
      </div>
      <ConfirmDialog
        open={confirm != null}
        title={confirm?.type === 'all' ? '清除全部历史？' : '删除这个任务？'}
        description={confirm?.type === 'all'
          ? '将删除所有已完成、失败、已取消或等待确认的任务；正在运行的任务会被保留。此操作不可撤销。'
          : `将删除「${confirm?.job?.title || confirm?.job?.url || ''}」及其本地总结/音频记录。此操作不可撤销。`}
        confirmLabel={confirm?.type === 'all' ? '清除全部' : '删除任务'}
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirm(null)}
      />
    </div>
  )
}
