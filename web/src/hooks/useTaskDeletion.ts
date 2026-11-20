import {useCallback, useEffect, useState} from 'react'
import {ApiError, deleteJob, type Job} from '../lib/api'
import {useToast} from '../components/ToastProvider'

const UNDO_WINDOW_MS = 5000
// Timers belong to this browser session, so navigating away cannot shorten the undo window.
const pending = new Map<string, number>()
const listeners = new Set<(id: string, committed: boolean) => void>()

function publish(id: string, committed = false) {
  for (const listener of listeners) listener(id, committed)
}

export function useTaskDeletion() {
  const toast = useToast()
  const [hidden, setHidden] = useState(() => new Set(pending.keys()))
  useEffect(() => {
    const onChange = (id: string, committed: boolean) => {
      setHidden(current => {
        const next = new Set(current)
        if (committed || pending.has(id)) next.add(id)
        else next.delete(id)
        return next
      })
    }
    listeners.add(onChange)
    return () => { listeners.delete(onChange) }
  }, [])

  const schedule = useCallback((job: Job) => {
    if (pending.has(job.id)) return
    const timer = window.setTimeout(async () => {
      // Keep the row hidden while the server processes the deletion.
      pending.set(job.id, 0)
      let committed = true
      try {
        await deleteJob(job.id)
      } catch (error) {
        committed = error instanceof ApiError && error.status === 404
        if (!committed) toast.error('删除失败', error instanceof Error ? error.message : '请重试')
      } finally {
        pending.delete(job.id)
        publish(job.id, committed)
      }
    }, UNDO_WINDOW_MS)
    pending.set(job.id, timer)
    publish(job.id)
    toast.success('已删除任务记录', '五秒内可以撤销', {
      taskName: job.title || undefined,
      durationMs: UNDO_WINDOW_MS,
      action: {
        label: '撤销',
        onClick: () => {
          if (pending.get(job.id) !== timer) return
          window.clearTimeout(timer)
          pending.delete(job.id)
          publish(job.id)
        },
      },
    })
  }, [toast])

  return {hidden, schedule}
}
