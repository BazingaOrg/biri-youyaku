export const SUMMARY_FLUSH_INTERVAL_MS = 150

/** Keep the newest snapshot and emit at a bounded rate, including a trailing flush. */
export function createSummaryThrottler(onSummary: (summary: string) => void) {
  let latestText: string | null = null
  let canceled = false
  let timerId: ReturnType<typeof setTimeout> | null = null

  const flush = () => {
    timerId = null
    if (canceled || latestText === null) return
    onSummary(latestText)
    latestText = null
  }

  return {
    push: (text: string) => {
      if (canceled) return
      latestText = text
      if (timerId === null) timerId = setTimeout(flush, SUMMARY_FLUSH_INTERVAL_MS)
    },
    cancel: () => {
      canceled = true
      if (timerId !== null) clearTimeout(timerId)
      timerId = null
      latestText = null
    },
  }
}
