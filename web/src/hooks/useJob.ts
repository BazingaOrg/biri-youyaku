import {useCallback, useEffect, useState} from 'react'
import {getJob, type Job} from '../lib/api'
import {isStatusNewer} from '../lib/jobStatus'

export function useJob(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!jobId) {
      return
    }
    try {
      const response = await getJob(jobId)
      setJob((current) => {
        // refresh 和 SSE patch 之间可能乱序：refresh 是 GET 快照，发出去到收到中间
        // SSE 可能已经推送了「更靠后的」状态。这里用 STATUS_ORDER 比较，避免把
        // SUMMARIZING / COMPLETED 这种已经收到的状态打回 TRANSCRIPT_READY。
        if (
          current != null &&
          current.id === response.job.id &&
          isStatusNewer(current.status, response.job.status)
        ) {
          // 保留 current 的 status 与已积累的 summary，其它字段以 response 为准
          // （拿最新 transcript / chapters / token_usage 等）
          return {
            ...response.job,
            status: current.status,
            summary: current.summary || response.job.summary,
            queued: current.queued,
          }
        }
        return response.job
      })
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载任务失败')
    }
  }, [jobId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return {job, setJob, error, refresh}
}
