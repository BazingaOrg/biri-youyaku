import {API_BASE_URL, getApiToken} from './api'

export type JobStreamEvent =
  | 'status'
  | 'meta'
  | 'summary_chunk'
  | 'download_progress'
  | 'transcribe_progress'
  | 'error'

export interface JobStreamMessage {
  event: JobStreamEvent
  data: string
}

export interface JobStreamSubscription {
  close: () => void
}

export function openJobStream(
  jobId: string,
  onMessage: (message: JobStreamMessage) => void,
  onError: (error: Error) => void,
  onClose?: () => void,
): JobStreamSubscription {
  const controller = new AbortController()

  void readStream(jobId, controller.signal, onMessage).catch((error) => {
    if (!controller.signal.aborted) {
      onError(error instanceof Error ? error : new Error('SSE stream failed'))
    }
  }).finally(() => {
    if (!controller.signal.aborted) {
      onClose?.()
    }
  })

  return {
    close: () => controller.abort(),
  }
}

async function readStream(
  jobId: string,
  signal: AbortSignal,
  onMessage: (message: JobStreamMessage) => void,
) {
  const headers = new Headers()
  const token = getApiToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}/v1/jobs/${jobId}/stream`, {
    headers,
    signal,
    credentials: 'include',
  })
  if (!response.ok || response.body == null) {
    throw new Error(`SSE stream failed: HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventName: JobStreamEvent = 'status'
  let dataLines: string[] = []

  const flush = () => {
    if (dataLines.length === 0) {
      return
    }
    onMessage({event: eventName, data: dataLines.join('\n')})
    eventName = 'status'
    dataLines = []
  }

  while (!signal.aborted) {
    const {value, done} = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, {stream: true})

    let lineEnd = buffer.indexOf('\n')
    while (lineEnd >= 0) {
      const rawLine = buffer.slice(0, lineEnd)
      buffer = buffer.slice(lineEnd + 1)
      const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine

      if (line === '') {
        flush()
      } else if (line.startsWith(':')) {
        // SSE heartbeat/comment line.
      } else if (line.startsWith('event:')) {
        eventName = line.slice(6).trim() as JobStreamEvent
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }

      lineEnd = buffer.indexOf('\n')
    }
  }

  flush()
}
