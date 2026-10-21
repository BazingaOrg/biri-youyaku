import {useCallback, useEffect, useState} from 'react'
import {listJobs, type Job} from '../lib/api'
import {isRunning} from '../lib/jobStatus'

const REFRESH_MS = 4000

export function useTaskAlerts() {
  const [running, setRunning] = useState<Job[]>([])
  const [failed, setFailed] = useState<Job[]>([])

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const [active, terminal] = await Promise.all([
        listJobs({active_only: true, limit: 20}, {signal}),
        listJobs({terminal_only: true, limit: 30}, {signal}),
      ])
      if (signal?.aborted) return
      setRunning(active.jobs.filter((job) => isRunning(job.status)))
      setFailed(terminal.jobs.filter((job) => job.status === 'FAILED'))
    } catch {
      if (signal?.aborted) return
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'hidden') return
      void refresh()
    }, REFRESH_MS)
    const onVis = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    document.addEventListener('visibilitychange', onVis)
    window.addEventListener('focus', onVis)
    return () => {
      controller.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVis)
      window.removeEventListener('focus', onVis)
    }
  }, [refresh])

  return {running, failed, badge: running.length + failed.length, refresh}
}
