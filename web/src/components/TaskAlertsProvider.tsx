import {useEffect, useMemo, useState} from 'react'
import type {ReactNode} from 'react'
import {listJobs} from '../lib/api'
import {isRunning} from '../lib/jobStatus'
import {createTaskAlertsRefresher, taskAlertRefreshDelay} from '../lib/taskAlerts'
import {TaskAlertsContext} from '../hooks/useTaskAlerts'
import type {TaskAlertsContextValue} from '../hooks/useTaskAlerts'

export function TaskAlertsProvider({children}: {children: ReactNode}) {
  const [running, setRunning] = useState<TaskAlertsContextValue['running']>([])
  const [failed, setFailed] = useState<TaskAlertsContextValue['failed']>([])
  const [refresher] = useState(() => createTaskAlertsRefresher({
    loadJobs: listJobs,
    isRunning,
    onUpdate: (update) => {
      setRunning(update.running)
      setFailed(update.failed)
    },
  }))
  const {refresh} = refresher
  const hasRunning = running.length > 0

  useEffect(() => {
    void refresh()
    return () => refresher.abort()
  }, [refresh, refresher])

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, taskAlertRefreshDelay(hasRunning))
    const onActivity = () => {
      if (document.visibilityState !== 'visible' || !refresher.shouldRefreshOnActivity()) return
      void refresh()
    }
    document.addEventListener('visibilitychange', onActivity)
    window.addEventListener('focus', onActivity)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onActivity)
      window.removeEventListener('focus', onActivity)
    }
  }, [hasRunning, refresh, refresher])

  const value = useMemo(
    () => ({running, failed, badge: running.length + failed.length, refresh: refresher.invalidate}),
    [failed, refresher, running],
  )
  return <TaskAlertsContext.Provider value={value}>{children}</TaskAlertsContext.Provider>
}
