import {useEffect, useRef} from 'react'
import type {Job, JobStatus} from '../lib/api'
import {openJobStream, type JobStreamMessage} from '../lib/sse'

// summary_chunk 由 LLM 流式推送，可能每秒几十次；用 rAF 合批到 60fps，避免
// ReactMarkdown 频繁重排。其它事件（status / progress）保持立即派发。
//
// 返回 {push, cancel}：cancel 用于 useEffect cleanup，确保 unmount 后挂着的 rAF /
// timeout 不会再调 onPatch（否则跨 jobId 切换时，旧 jobId 的 summary 会被写到新 jobId
// 上，React 也会 warn 「Cannot update unmounted component」）。
function createSummaryThrottler(onPatch: (patch: Partial<Job>) => void) {
  let latestText: string | null = null
  let canceled = false
  let rafId: number | null = null
  let timerId: ReturnType<typeof setTimeout> | null = null
  const flush = () => {
    rafId = null
    timerId = null
    if (canceled || latestText === null) return
    onPatch({summary: latestText})
    latestText = null
  }
  const push = (text: string) => {
    if (canceled) return
    latestText = text
    if (rafId !== null || timerId !== null) return
    if (typeof window !== 'undefined' && 'requestAnimationFrame' in window) {
      rafId = window.requestAnimationFrame(flush)
    } else {
      timerId = setTimeout(flush, 16)
    }
  }
  const cancel = () => {
    canceled = true
    if (rafId !== null && typeof window !== 'undefined') {
      window.cancelAnimationFrame(rafId)
      rafId = null
    }
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
    latestText = null
  }
  return {push, cancel}
}

interface StatusPayload {
  status: JobStatus
  summary?: string
  message?: string
  stage?: string
  error_code?: string
  email_error?: string | null
}

interface UseJobStreamOptions {
  /** SSE 重新建立连接（不是首次连接）后触发；调 refresh 拉一次 snapshot 修正漂移 */
  onReconnected?: () => void
}

export function useJobStream(
  jobId: string | null,
  onPatch: (patch: Partial<Job>) => void,
  options: UseJobStreamOptions = {},
) {
  const terminalRef = useRef(false)
  const onReconnectedRef = useRef(options.onReconnected)
  // 把回调放进 ref 避免 useEffect 因 options 引用变化反复重建 SSE
  useEffect(() => {
    onReconnectedRef.current = options.onReconnected
  }, [options.onReconnected])

  useEffect(() => {
    if (!jobId) {
      return undefined
    }

    let closed = false
    let subscription: {close: () => void} | null = null
    let attempts = 0
    let isReconnect = false
    terminalRef.current = false
    const throttler = createSummaryThrottler(onPatch)
    const pushSummary = throttler.push

    const handleMessage = (message: JobStreamMessage) => {
      if (message.event === 'status') {
        const payload = JSON.parse(message.data) as StatusPayload
        terminalRef.current = ['COMPLETED', 'FAILED', 'CANCELED'].includes(payload.status)
        const patch: Partial<Job> = {
          status: payload.status,
        }
        if (payload.summary !== undefined) {
          patch.summary = payload.summary
        }
        if (payload.message !== undefined) {
          patch.error_message = payload.message
        }
        if (payload.stage !== undefined) {
          patch.error_stage = payload.stage
        }
        if (payload.error_code !== undefined) {
          patch.error_code = payload.error_code
        }
        if (payload.email_error !== undefined) {
          patch.email_error = payload.email_error
        }
        onPatch(patch)
        return
      }
      if (message.event === 'meta') {
        onPatch(JSON.parse(message.data) as Partial<Job>)
        return
      }
      if (message.event === 'summary_chunk') {
        const payload = JSON.parse(message.data) as {text: string}
        // rAF 合批，避免高频 setState 拖慢 ReactMarkdown
        pushSummary(payload.text)
        return
      }
      if (message.event === 'download_progress') {
        onPatch({download_progress: JSON.parse(message.data) as Job['download_progress']})
        return
      }
      if (message.event === 'transcribe_progress') {
        onPatch({transcribe_progress: JSON.parse(message.data) as Job['transcribe_progress']})
        return
      }
      if (message.event === 'error') {
        const payload = JSON.parse(message.data) as {stage?: string; message?: string}
        terminalRef.current = true
        onPatch({status: 'FAILED', error_stage: payload.stage, error_message: payload.message})
      }
    }

    const connect = () => {
      subscription = openJobStream(
        jobId,
        (message) => {
          // 收到第一条消息视为连接成功；若是「重连后的首条」就触发 onReconnected
          // 让上层 refresh snapshot，弥补断流期间漏掉的事件。
          if (attempts > 0 && isReconnect) {
            isReconnect = false
            onReconnectedRef.current?.()
          }
          attempts = 0
          handleMessage(message)
        },
        (error) => {
          if (!terminalRef.current) {
            onPatch({error_message: error.message})
          }
        },
        () => {
          if (closed || terminalRef.current) {
            return
          }
          const delays = [1000, 2000, 5000]
          const delay = delays[Math.min(attempts, delays.length - 1)]
          attempts += 1
          isReconnect = true  // 下一次 connect 是重连，首条消息回来时通知上层
          window.setTimeout(() => {
            if (!closed) {
              connect()
            }
          }, delay)
        },
      )
    }

    connect()
    return () => {
      closed = true
      subscription?.close()
      // 取消未 flush 的 rAF / setTimeout，避免对 unmounted / 切换后的 jobId 派发
      throttler.cancel()
    }
  }, [jobId, onPatch])
}
