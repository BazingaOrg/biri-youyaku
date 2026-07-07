import {useEffect, useRef} from 'react'
import type {DistillRunStatus, DistillStatusPayload} from '../lib/api'
import {openDistillStream, type DistillStreamMessage} from '../lib/sse'

const TERMINAL_STATUSES: DistillRunStatus[] = ['COMPLETED', 'FAILED', 'CANCELLED']

/**
 * 订阅某个蒸馏 run 的 SSE 进度。跟 useJobStream 同一套重连策略（瞬时错误不视为
 * 终态，退避重连），但负载简单得多——只有一种 `status` 事件、不需要节流。
 */
export function useDistillStream(runId: string | null, onPatch: (payload: DistillStatusPayload) => void) {
  const terminalRef = useRef(false)

  useEffect(() => {
    if (!runId) {
      return undefined
    }

    let closed = false
    let subscription: {close: () => void} | null = null
    let attempts = 0
    terminalRef.current = false

    const handleMessage = (message: DistillStreamMessage) => {
      if (message.event !== 'status') return
      const payload = JSON.parse(message.data) as DistillStatusPayload
      terminalRef.current = TERMINAL_STATUSES.includes(payload.status)
      onPatch(payload)
    }

    const connect = () => {
      subscription = openDistillStream(
        runId,
        (message) => {
          attempts = 0
          handleMessage(message)
        },
        (error) => {
          if (!terminalRef.current) {
            console.debug('[useDistillStream] transient SSE error, will reconnect:', error.message)
          }
        },
        () => {
          if (closed || terminalRef.current) return
          const delays = [1000, 2000, 5000]
          const delay = delays[Math.min(attempts, delays.length - 1)]
          attempts += 1
          window.setTimeout(() => {
            if (!closed) connect()
          }, delay)
        },
      )
    }

    connect()
    return () => {
      closed = true
      subscription?.close()
    }
  }, [runId, onPatch])
}
