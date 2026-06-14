import {useCallback, useEffect, useRef, useState} from 'react'
import {getJob, type Job} from '../lib/api'
import {isStatusNewer} from '../lib/jobStatus'

/**
 * 拉取并缓存单个 job 的快照。负责处理两个 race window：
 *
 * 1. 切 jobId 时立刻清空旧 state，避免一闪显示前一个任务的标题 / 进度 / 总结。
 * 2. AbortController 取消上一个 fetch：A→B→A 快速跳转时，旧请求晚到不会覆盖新 state。
 *    同时用 `signal.aborted` 双保险跳过状态写入（避免 setState 落到已 unmount 组件）。
 */
export function useJob(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  const refresh = useCallback(async () => {
    if (!jobId) return
    // 取消上一个挂着的请求（手动 refresh 也走这条路：last-write-wins）
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    try {
      const response = await getJob(jobId, {signal: controller.signal})
      if (controller.signal.aborted) return
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
      // AbortError 是预期信号（jobId 切换或卸载），不写到 UI
      if (controller.signal.aborted) return
      setError(err instanceof Error ? err.message : '加载任务失败')
    }
  }, [jobId])

  useEffect(() => {
    // jobId 变化（含进入 / 离开）→ 立刻清空旧数据，杜绝跨任务串数据
    setJob(null)
    setError(null)
    if (!jobId) {
      controllerRef.current?.abort()
      return
    }
    void refresh()
    return () => {
      // unmount / 下一次 jobId 变化前：把挂着的请求 abort 掉
      controllerRef.current?.abort()
    }
  }, [jobId, refresh])

  return {job, setJob, error, refresh}
}
