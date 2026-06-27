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
  /** UP 主 uid，用于跳「该 UP 全部投稿」页；老任务可能为空。 */
  mid?: number
  title?: string
  author?: string
  duration?: number
  status: JobStatus
  error_stage?: string
  error_message?: string
  error_code?: string
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
  /** 列表（lite）响应不带 summary 全文，仅用此布尔标记是否有总结；详情接口才返回 summary。 */
  summary_available?: boolean
  created_at: number
  updated_at: number
  completed_at?: number
  stream_finished_at?: number
  token_usage?: Record<string, unknown>
  stage_timings: Array<{
    stage: string
    started_at: number
    ended_at: number
    duration_ms: number
  }>
  download_progress?: {
    status?: string
    downloaded_bytes?: number
    total_bytes?: number
    percent?: number
    speed?: number
    eta?: number
  }
  transcribe_progress?: {
    percent?: number
    items_count?: number
    preview?: string
  }
  options: JobOptions
  option_overrides: JobOptionOverrides
  audio_available: boolean
  /** 邮件发送失败时的原因；存在时表示总结已完成但邮件未送达。 */
  email_error?: string | null
  /** 主题标签（总结完成后由 LLM 提炼；历史任务可能为空）。 */
  tags?: string[]
  /** 后端 transient 标记：true = 当前阶段正在等并发槽位（_io_semaphore / _summary_semaphore）。 */
  queued?: boolean
  /** 长视频分段总结进度（transient，仅 SSE 推送）：done=已完成段数，total=总段数。 */
  summary_segment?: {done: number; total: number}
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:17821'
// Token is purely a deployment concern: backed by VITE_API_TOKEN at build
// time. Leave it empty during local dev (with backend API_TOKEN also empty)
// to skip auth entirely. There is no end-user prompt for this value.
const API_TOKEN = (import.meta.env.VITE_API_TOKEN ?? '').trim()

export function getApiToken() {
  return API_TOKEN
}

/** 带 HTTP status 的错误，调用方可据此区分 404 / 409 等（如删除时 404 = 已不存在）。 */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  const token = getApiToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: init.credentials ?? 'include',
  })
  if (!response.ok) {
    // 429 走友好提示：服务器（或 CF）限流，不是用户姿势错
    if (response.status === 429) {
      const retryAfter = response.headers.get('retry-after')
      const hint = retryAfter ? `请 ${retryAfter}s 后再试` : '请稍后再试'
      throw new Error(`操作太频繁，${hint}`)
    }
    // 503：在飞任务到上限了
    if (response.status === 503) {
      try {
        const payload = await response.clone().json() as {detail?: string}
        if (payload.detail) throw new Error(payload.detail)
      } catch { /* fall through */ }
      throw new Error('服务器繁忙，请稍后再试')
    }
    const message = await response.text()
    throw new ApiError(response.status, message || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function requestBlob(path: string): Promise<{blob: Blob; filename?: string}> {
  const headers = new Headers()
  const token = getApiToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
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

export interface RuntimeConfig {
  ok: true
  auth_mode: 'api_token' | 'none'
  llm_configured: boolean
  email_configured: boolean
  bilibili_cookie_configured: boolean
}

export function getRuntimeConfig() {
  return request<RuntimeConfig>('/v1/config/runtime')
}

export function createJob(url: string, options: JobOptionOverrides) {
  // deduped: 后端发现这条视频之前已总结完成，直接复用了旧任务（没有新建、没有再烧 token）。
  return request<{ok: true; job_id: string; deduped?: boolean}>('/v1/jobs', {
    method: 'POST',
    body: JSON.stringify({url, options}),
  })
}

// 注：后端还有这些 endpoint 前端零调用、对应 client 函数已删（留着会被当成「半成品 API」误用）：
// POST /v1/jobs/preview、POST /v1/llm/models、POST /v1/jobs/{id}/transcript、
// POST /v1/jobs/{id}/resume（总结改为服务端自动续跑后不再需要前端驱动）、GET /v1/usage。
// 真要接入时去 routes/jobs.py / routes/config.py 看签名重新加。

export function getJob(jobId: string, init?: RequestInit) {
  // init 主要是为了 useJob 透传 AbortController.signal：jobId 切换时取消上一个请求，
  // 避免旧 jobId 的响应晚到覆盖新 jobId 的数据。
  return request<{ok: true; job: Job}>(`/v1/jobs/${jobId}`, init)
}

export function retryJob(jobId: string, options: JobOptionOverrides = {}) {
  return request<{ok: true}>(`/v1/jobs/${jobId}/retry`, {
    method: 'POST',
    body: JSON.stringify({options}),
  })
}

export function listJobs(params: {limit?: number; offset?: number; cursor?: number | null} = {}) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit ?? 50))
  if (params.offset) {
    search.set('offset', String(params.offset))
  }
  if (params.cursor != null) {
    search.set('cursor', String(params.cursor))
  }
  return request<{ok: true; jobs: Job[]; next_cursor?: number | null}>(`/v1/jobs?${search.toString()}`)
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

export interface UpVideo {
  bvid: string
  title: string
  cover: string
  /** 发布时间，unix 秒。 */
  pubdate: number
  /** 时长，秒。 */
  duration: number
  url: string
  /** 该 bvid 是否已有任务及其状态；null = 从未总结过。 */
  status: JobStatus | null
  job_id: string | null
}

export interface UpVideosResponse {
  ok: true
  mid: number
  author: string
  total: number
  page: number
  page_size: number
  has_more: boolean
  videos: UpVideo[]
}

export function resolveUp(input: string) {
  return request<{ok: true; mid: number}>(`/v1/up/resolve?input=${encodeURIComponent(input)}`)
}

export type UpOrder = 'pubdate' | 'click'

export function getUpVideos(
  mid: number,
  params: {page?: number; keyword?: string; order?: UpOrder} = {},
) {
  const search = new URLSearchParams()
  search.set('page', String(params.page ?? 1))
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.order) search.set('order', params.order)
  return request<UpVideosResponse>(`/v1/up/${mid}/videos?${search.toString()}`)
}

export {API_BASE_URL}
