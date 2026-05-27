import {useEffect} from 'react'
import type {Job, JobStatus} from '../lib/api'
import {openJobStream, type JobStreamMessage} from '../lib/sse'

interface StatusPayload {
  status: JobStatus
  summary?: string
  message?: string
  stage?: string
}

export function useJobStream(jobId: string | null, onPatch: (patch: Partial<Job>) => void) {
  useEffect(() => {
    if (!jobId) {
      return undefined
    }

    const handleMessage = (message: JobStreamMessage) => {
      if (message.event === 'status') {
        const payload = JSON.parse(message.data) as StatusPayload
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
      if (message.event === 'error') {
        const payload = JSON.parse(message.data) as {stage?: string; message?: string}
        onPatch({status: 'FAILED', error_stage: payload.stage, error_message: payload.message})
      }
    }

    const source = openJobStream(jobId, handleMessage, (error) => {
      onPatch({error_message: error.message})
    })
    return () => source.close()
  }, [jobId, onPatch])
}
