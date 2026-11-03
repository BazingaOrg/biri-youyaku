import type {Job} from './api'

export const ACTIVE_TASK_ALERT_REFRESH_MS = 4000
// Idle fallback still notices tasks started in another tab or on another device.
export const IDLE_TASK_ALERT_REFRESH_MS = 60_000
const ACTIVITY_REFRESH_THROTTLE_MS = 1000

interface JobsPage {
  jobs: Job[]
}

type LoadJobs = (
  params: {active_only?: boolean; terminal_only?: boolean; limit: number},
  init: {signal: AbortSignal},
) => Promise<JobsPage>

interface TaskAlertUpdate {
  running: Job[]
  failed: Job[]
}

interface TaskAlertsRefresherOptions {
  loadJobs: LoadJobs
  isRunning: (status: Job['status']) => boolean
  onUpdate: (update: TaskAlertUpdate) => void
  now?: () => number
}

export function taskAlertRefreshDelay(hasRunning: boolean) {
  return hasRunning ? ACTIVE_TASK_ALERT_REFRESH_MS : IDLE_TASK_ALERT_REFRESH_MS
}

/** Coordinates one shared request pair, including StrictMode abort/restart. */
export function createTaskAlertsRefresher({
  loadJobs,
  isRunning,
  onUpdate,
  now = Date.now,
}: TaskAlertsRefresherOptions) {
  let inFlight: Promise<void> | null = null
  let controller: AbortController | null = null
  let lastStartedAt = -Infinity
  let lifecycleGeneration = 0

  const refresh = () => {
    if (inFlight) return inFlight

    const currentController = new AbortController()
    controller = currentController
    lastStartedAt = now()
    const performRequest = async () => {
      try {
        const [active, terminal] = await Promise.all([
          loadJobs({active_only: true, limit: 20}, {signal: currentController.signal}),
          loadJobs({terminal_only: true, limit: 30}, {signal: currentController.signal}),
        ])
        if (currentController.signal.aborted) return
        onUpdate({
          running: active.jobs.filter((job) => isRunning(job.status)),
          failed: terminal.jobs.filter((job) => job.status === 'FAILED'),
        })
      } catch {
        // Polling is best-effort; the next activity or timer can retry.
      } finally {
        if (inFlight === request) inFlight = null
        if (controller === currentController) controller = null
      }
    }
    const request = performRequest()
    inFlight = request
    return request
  }

  return {
    refresh,
    invalidate: (): Promise<void> => {
      // Mutations need a snapshot started after the mutation. If an older
      // request is still running, chain one trailing refresh without overlap.
      if (inFlight) {
        const generation = lifecycleGeneration
        return inFlight.then(() => {
          if (generation === lifecycleGeneration) return refresh()
        })
      }
      return refresh()
    },
    abort: () => {
      lifecycleGeneration += 1
      controller?.abort()
      controller = null
      // A StrictMode effect restart can immediately create a fresh request.
      // Identity checks in finally prevent the aborted request clearing it.
      inFlight = null
    },
    shouldRefreshOnActivity: () => now() - lastStartedAt >= ACTIVITY_REFRESH_THROTTLE_MS,
  }
}
