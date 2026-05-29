import {useEffect, useRef} from 'react'
import type {Job, JobStatus} from '../lib/api'
import {openJobStream, type JobStreamMessage} from '../lib/sse'

interface StatusPayload {
  status: JobStatus
  summary?: string
  message?: string
  stage?: string
  error_code?: string
}

export function useJobStream(jobId: string | null, onPatch: (patch: Partial<Job>) => void) {
  const terminalRef = useRef(false)

  useEffect(() => {
    if (!jobId) {
      return undefined
    }

    let closed = false
    let subscription: {close: () => void} | null = null
    let attempts = 0
    terminalRef.current = false

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
        onPatch(patch)
        return
      }
      if (message.event === 'meta') {
        onPatch(JSON.parse(message.data) as Partial<Job>)
        return
      }
      if (message.event === 'summary_chunk') {
        const payload = JSON.parse(message.data) as {text: string}
        onPatch({summary: payload.text})
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
    }
  }, [jobId, onPatch])
}
