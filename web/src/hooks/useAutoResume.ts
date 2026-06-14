import {useEffect, useRef} from 'react'
import {resumeJob, type ConfigDefaults, type Job, type JobOptionOverrides} from '../lib/api'
import {useToast} from '../components/ToastProvider'

/**
 * `TRANSCRIPT_READY` 自动 resume —— 不再二次确认。
 *
 * 只在 `status === TRANSCRIPT_READY` 这一刻锁；一旦离开（不论是进 SUMMARIZING 还是
 * retry 回到 PENDING）就清锁。否则同一 jobId 的 retry 会因为「之前 resume 过」而被
 * 跳过，整条 pipeline 卡在 TRANSCRIPT_READY 永远不再向前走。
 *
 * 等 defaults 拉到再 auto-resume：否则旧 job 的 kimi 快照会被原样回放，defaults
 * 拉到后 useEffect 会因 overrides 变化而重跑。
 */
export function useAutoResume(
  job: Job | null,
  jobId: string | null,
  defaults: ConfigDefaults | null,
  overrides: JobOptionOverrides,
  refresh: () => Promise<void> | void,
) {
  const toast = useToast()
  const autoResumedRef = useRef<string | null>(null)

  // 切任务时清锁
  useEffect(() => {
    autoResumedRef.current = null
  }, [jobId])

  useEffect(() => {
    if (!job || !jobId) return
    if (job.status !== 'TRANSCRIPT_READY') {
      if (autoResumedRef.current === jobId) {
        autoResumedRef.current = null
      }
      return
    }
    if (!defaults) return
    if (autoResumedRef.current === jobId) return
    autoResumedRef.current = jobId
    void resumeJob(jobId, overrides)
      .then(() => refresh())
      .catch((err) => {
        const message = err instanceof Error ? err.message : '继续处理失败'
        toast.error('继续处理失败', message, {taskName: job.title || undefined})
      })
  }, [job, jobId, refresh, toast, defaults, overrides])
}
