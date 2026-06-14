import {useEffect, useRef} from 'react'
import type {Job} from '../lib/api'
import {isTerminal} from '../lib/jobStatus'
import {clearActive} from '../lib/activeJob'
import {friendlyError} from '../lib/errorMap'
import {useToast} from '../components/ToastProvider'

/**
 * 终态 toast 与 localStorage 清理。
 *
 * - `notifiedRef`：去重每个 `<jobId>:<status>` 的 toast，离开终态时清掉（让 retry
 *   后再次进入 FAILED 时还能再弹一次）。
 * - `sawRunningRef`：只在「本会话里观察到 running 状态」的转移上弹 toast；直接打开
 *   已完成 / 失败 / 取消的历史任务时跳过 toast，但仍做 `clearActive` 兜底（带 jobId
 *   参数会自动跳过不匹配的 active 指针，安全）。
 *
 * 切换 jobId 时两个 ref 都会清空，避免跨任务残留。
 */
export function useTerminalToast(job: Job | null, jobId: string | null) {
  const toast = useToast()
  const notifiedRef = useRef<string | null>(null)
  const sawRunningRef = useRef<string | null>(null)

  // 切换任务时重置两个一次性 flag
  useEffect(() => {
    notifiedRef.current = null
    sawRunningRef.current = null
  }, [jobId])

  useEffect(() => {
    if (!job || !jobId) return
    if (!isTerminal(job.status)) {
      sawRunningRef.current = jobId
      notifiedRef.current = null
      return
    }
    const key = `${jobId}:${job.status}`
    if (notifiedRef.current === key) return
    notifiedRef.current = key
    clearActive(jobId)
    // 没在本会话里见过 running 状态 → 是「直接打开历史任务」，不弹 toast
    if (sawRunningRef.current !== jobId) return
    const taskName = job.title || undefined
    if (job.status === 'COMPLETED') {
      const detail = !job.options.email_enabled
        ? '已生成'
        : job.email_error
          ? '总结已生成，邮件未送达'
          : '已发送到邮箱'
      toast.success('总结完成', detail, {taskName})
    }
    if (job.status === 'FAILED' && job.error_message) {
      const fe = friendlyError(job.error_code, job.error_message, job.error_stage)
      toast.error(fe.title, fe.message, {taskName})
    }
    // CANCELED 不弹 toast：按钮即时反馈已经在 cancel() 里以 info 形式发过
  }, [job, jobId, toast])
}
