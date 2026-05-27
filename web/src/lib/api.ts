export type JobStatus =
  | 'PENDING'
  | 'FETCHING_META'
  | 'DOWNLOADING_AUDIO'
  | 'TRANSCRIBING'
  | 'TRANSCRIPT_READY'
  | 'SUMMARIZING'
  | 'EMAILING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELED'

export interface JobOptions {
  task_type: 'summary' | 'audio'
  language: string
  force_asr: boolean
  summary_language: string
  email_enabled: boolean
  email_recipient?: string
  email_subject_template: string
  llm_base_url: string
  llm_model: string
  prompt_template?: string
}

export type JobOptionOverrides = Partial<JobOptions> & {
  llm_api_key?: string
}

export interface ConfigDefaults extends JobOptions {
  llm_api_key_configured: boolean
  asr_model: string
  asr_language: string
  audio_download_enabled: boolean
}

export interface Job {
  id: string
  url: string
  bvid?: string
  cid?: number
  title?: string
  author?: string
  duration?: number
  status: JobStatus
  error_stage?: string
  error_message?: string
  subtitle_source?: string
  chapters: Array<{
    start: number
    end?: number
    title: string
  }>
  transcript: Array<{
    start: number
    end: number
    text: string
  }>
  summary?: string
  created_at: number
  updated_at: number
  completed_at?: number
  options: JobOptions
  option_overrides: JobOptionOverrides
  audio_available: boolean
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:17821'
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? ''

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (API_TOKEN) {
    headers.set('Authorization', `Bearer ${API_TOKEN}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: init.credentials ?? 'include',
  })
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function requestBlob(path: string): Promise<{blob: Blob; filename?: string}> {
  const headers = new Headers()
  if (API_TOKEN) {
    headers.set('Authorization', `Bearer ${API_TOKEN}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers,
    credentials: 'include',
  })
  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const payload = await response.json() as {detail?: string}
      message = payload.detail ?? message
    } catch {
      const text = await response.text()
      if (text) {
        message = text
      }
    }
    throw new Error(message)
  }

  const disposition = response.headers.get('content-disposition') ?? ''
  const filenameMatch = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/)
  const filename = filenameMatch?.[1] ? decodeURIComponent(filenameMatch[1]) : filenameMatch?.[2]
  return {blob: await response.blob(), filename}
}

export function getConfigDefaults() {
  return request<{ok: true; defaults: ConfigDefaults}>('/v1/config/defaults')
}

export function createJob(url: string, options: JobOptionOverrides) {
  return request<{ok: true; job_id: string}>('/v1/jobs', {
    method: 'POST',
    body: JSON.stringify({url, options}),
  })
}

export function discoverLlmModels(params: {llm_base_url?: string; llm_api_key?: string}) {
  return request<{ok: true; models: string[]}>('/v1/llm/models', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function getJob(jobId: string) {
  return request<{ok: true; job: Job}>(`/v1/jobs/${jobId}`)
}

export function resumeJob(jobId: string, options: JobOptionOverrides = {}) {
  return request<{ok: true}>(`/v1/jobs/${jobId}/resume`, {
    method: 'POST',
    body: JSON.stringify({options}),
  })
}

export function listJobs() {
  return request<{ok: true; jobs: Job[]}>('/v1/jobs?limit=50')
}

export function resendEmail(jobId: string) {
  return request<{ok: true}>(`/v1/jobs/${jobId}/email`, {method: 'POST'})
}

export function cancelJob(jobId: string) {
  return request<{ok: true}>(`/v1/jobs/${jobId}/cancel`, {method: 'POST'})
}

export function deleteJob(jobId: string) {
  return request<{ok: true}>(`/v1/jobs/${jobId}`, {method: 'DELETE'})
}

export function deleteAllJobs() {
  return request<{ok: true; deleted_count: number; skipped_count: number}>('/v1/jobs', {method: 'DELETE'})
}

export function downloadJobAudio(jobId: string) {
  return requestBlob(`/v1/jobs/${jobId}/audio`)
}

export {API_BASE_URL, API_TOKEN}
