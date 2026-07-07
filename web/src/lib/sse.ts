import {API_BASE_URL, getApiToken} from './api'

export type JobStreamEvent =
  | 'status'
  | 'meta'
  | 'summary_chunk'
  | 'summary_segment'
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
  return openStream(`/v1/jobs/${jobId}/stream`, onMessage, onError, onClose)
}

// 作者蒸馏进度：同一套 SSE 帧格式，事件只有 `status`（见 routes/distill.py）。
export type DistillStreamEvent = 'status'

export interface DistillStreamMessage {
  event: DistillStreamEvent
  data: string
}

export function openDistillStream(
  runId: string,
  onMessage: (message: DistillStreamMessage) => void,
  onError: (error: Error) => void,
  onClose?: () => void,
): JobStreamSubscription {
  return openStream(`/v1/distill/${runId}/events`, onMessage, onError, onClose)
}

function openStream<TMessage extends {event: string; data: string}>(
  path: string,
  onMessage: (message: TMessage) => void,
  onError: (error: Error) => void,
  onClose?: () => void,
): JobStreamSubscription {
  const controller = new AbortController()

  void readStream(path, controller.signal, onMessage).catch((error) => {
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

async function readStream<TMessage extends {event: string; data: string}>(
  path: string,
  signal: AbortSignal,
  onMessage: (message: TMessage) => void,
) {
  const headers = new Headers()
  const token = getApiToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
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
  let eventName = 'status'
  let dataLines: string[] = []

  const flush = () => {
    if (dataLines.length === 0) {
      return
    }
    onMessage({event: eventName, data: dataLines.join('\n')} as TMessage)
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
        eventName = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }

      lineEnd = buffer.indexOf('\n')
    }
  }

  flush()
}
