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

  const requestInit = {
    ...init,
    headers,
    credentials: init.credentials ?? 'include',
  }
  const url = `${API_BASE_URL}${path}`
  let response: Response
  try {
    response = await fetch(url, requestInit)
  } catch (error) {
    const method = init.method?.toUpperCase() ?? 'GET'
    if (!(error instanceof TypeError) || method !== 'GET' || init.signal?.aborted) throw error
    await new Promise((resolve) => window.setTimeout(resolve, 500))
    response = await fetch(url, requestInit)
  }
  if (!response.ok) {
    // 429 走友好提示：服务器（或 CF）限流，不是用户姿势错
    if (response.status === 429) {
      const retryAfter = response.headers.get('retry-after')
      const hint = retryAfter ? `请 ${retryAfter}s 后再试` : '请稍后再试'
      throw new Error(`操作太频繁，${hint}`)
    }
    // 503：在飞任务到上限了
    if (response.status === 503) {
      throw new Error((await getErrorMessage(response)) || '服务器繁忙，请稍后再试')
    }
    throw new ApiError(response.status, (await getErrorMessage(response)) || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function getErrorMessage(response: Response): Promise<string> {
  const text = await response.text()
  if (!text) return ''
  try {
    const payload: unknown = JSON.parse(text)
    if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
      const {detail, message} = payload as {detail?: unknown; message?: unknown}
      if (typeof detail === 'string') return detail
      if (Object.prototype.hasOwnProperty.call(payload, 'detail')) return '请求失败，请稍后再试'
      if (typeof message === 'string') return message
    }
  } catch {
    // 非 JSON 错误响应直接展示文本。
  }
  return text
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
    throw new Error((await getErrorMessage(response)) || `HTTP ${response.status}`)
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
  knowledge_search_enabled?: boolean
}

export interface KnowledgeSearchHit {
  chunk_id: string
  document_id: string
  summary_revision_id?: string
  content_revision_id?: string
  title?: string | null
  author?: string | null
  bvid?: string | null
  source_url?: string | null
  heading_path: string
  snippet: string
  chunk_text?: string
  score: number
  source_level: 'summary' | 'transcript'
  locator?: string
  start_sec?: number
  end_sec?: number
  subtitle_source?: string | null
}

export interface KnowledgeCitation {
  id: string
  source_level: 'summary' | 'transcript'
  heading_path: string
  document_id: string
  title?: string | null
  locator: string
  start_sec?: number
  end_sec?: number
  subtitle_source?: string | null
}

export interface KnowledgeStatus {
  ok: true
  documents: number
  documents_deleted?: number
  chunks: number
  summary_chunks?: number
  transcript_chunks?: number
  search_enabled: boolean
  register_enabled: boolean
  transcript_index_enabled?: boolean
}

export function searchKnowledge(q: string, limit = 10) {
  const params = new URLSearchParams()
  params.set('q', q)
  params.set('limit', String(limit))
  return request<{ok: true; query: string; hits: KnowledgeSearchHit[]}>(
    `/v1/knowledge/search?${params.toString()}`,
  )
}

export function getKnowledgeStatus() {
  return request<KnowledgeStatus>('/v1/knowledge/status')
}

export function getRuntimeConfig() {
  return request<RuntimeConfig>('/v1/config/runtime')
}

export interface LlmBalanceResponse {
  ok: true
  supported: boolean
  provider?: string
  balance?: number
  currency?: string
}

export function getLlmBalance(refresh = false) {
  const suffix = refresh ? '?refresh=true' : ''
  return request<LlmBalanceResponse>(`/v1/llm/balance${suffix}`)
}

export type CostStatus = 'confirmed' | 'pending' | 'not_supported'

export interface CostAmount {
  currency: string
  micros: number
}

export interface CostOperation extends CostAmount {
  operation: string
  requests: number
}

export interface WeeklyCost extends CostAmount {
  /** 用户时区的周一日期（YYYY-MM-DD）。 */
  week_start: string
}

export interface BalanceSnapshot {
  provider: string
  balance_micros: number
  currency: string
  scope: 'account_balance' | 'key_limit' | 'account_credits'
  observed_at: number
}

/** 供应商确认的费用与请求用量；金额绝不会由 tokens 或静态费率估算。 */
export interface CostSummaryResponse {
  ok: true
  current_balance: {provider: string; balance: number; currency: string; scope: 'account_balance' | 'key_limit' | 'account_credits'} | null
  tracking_started_at: number | null
  timezone: string
  current_week_start: string
  tokens: {
    input_tokens: number
    output_tokens: number
    total_tokens: number
    /** 全部已记录 tokens：逐请求事件 + 尚无事件的旧 jobs.token_usage_json，互斥不双算。 */
    all_recorded_input_tokens: number
    all_recorded_output_tokens: number
    all_recorded_total_tokens: number
    legacy_input_tokens: number
    legacy_output_tokens: number
    legacy_total_tokens: number
    confirmed_requests: number
    pending_requests: number
    unsupported_requests: number
  }
  confirmed_costs: CostAmount[]
  by_operation: CostOperation[]
  balances: BalanceSnapshot[]
  weekly: WeeklyCost[]
}

export function getCostSummary(refreshBalance = false) {
  return request<CostSummaryResponse>(`/v1/stats/costs${refreshBalance ? '?refresh_balance=true' : ''}`)
}

export function createJob(url: string, options: JobOptionOverrides, params: {dedupe?: boolean} = {}) {
  // deduped: 后端发现这条视频之前已总结完成，直接复用了旧任务（没有新建、没有再烧 token）。
  return request<{ok: true; job_id: string; deduped?: boolean}>('/v1/jobs', {
    method: 'POST',
    body: JSON.stringify({url, options, dedupe: params.dedupe}),
  })
}

export function resummarizeJob(jobId: string, options: JobOptionOverrides) {
  return request<{ok: true; job_id: string}>(`/v1/jobs/${jobId}/resummarize`, {
    method: 'POST',
    body: JSON.stringify({options}),
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

export interface HistoryFilters {
  query?: string
  author?: string
  tag?: string
}

export function listJobs(params: HistoryFilters & {limit?: number; offset?: number; cursor?: string | number | null; active_only?: boolean; terminal_only?: boolean} = {}, init?: RequestInit) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit ?? 50))
  if (params.offset) {
    search.set('offset', String(params.offset))
  }
  if (params.cursor != null) {
    search.set('cursor', String(params.cursor))
  }
  if (params.active_only) search.set('active_only', 'true')
  if (params.terminal_only) search.set('terminal_only', 'true')
  for (const key of ['query', 'author', 'tag'] as const) {
    if (params[key]) search.set(key, params[key]!)
  }
  return request<{ok: true; jobs: Job[]; next_cursor?: string | number | null}>(`/v1/jobs?${search.toString()}`, init)
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

export interface BulkDeleteQuery {
  query?: string
  author?: string
  tag?: string
}

export interface BulkDeletePreview {
  ok: true
  matched_count: number
  by_status: Partial<Record<'COMPLETED' | 'FAILED' | 'CANCELED', number>>
  sample: Array<{id: string; title?: string; author?: string; completed_at?: number; created_at?: number}>
  sample_truncated_count: number
  preview_token: string
  /** 预览令牌的过期时间；旧服务端可能不返回，执行时仍会以 409 拒绝过期令牌。 */
  expires_at: number
}

/** 预览与执行均由服务端用完整数据库查询，绝不以当前已加载/可见条目为删除边界。 */
export function previewBulkDelete(filters: BulkDeleteQuery) {
  return request<BulkDeletePreview>('/v1/jobs/bulk-delete/preview', {
    method: 'POST',
    body: JSON.stringify(filters),
  })
}

export function executeBulkDelete(previewToken: string) {
  return request<{
    ok: true
    deleted_count: number
    cleanup_pending_count?: number
    cleanup_failures?: Array<{job_id: string; file_type: 'audio' | 'summary' | 'subtitle'}>
  }>('/v1/jobs/bulk-delete/execute', {
    method: 'POST',
    body: JSON.stringify({preview_token: previewToken}),
  })
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

// ---------------------------------------------------------------------------
// 作者蒸馏语料（distill）
// ---------------------------------------------------------------------------

export type DistillRunStatus =
  | 'PENDING'
  /** Legacy status from older runs; treated as in-progress / 准备中 in UI. */
  | 'FETCHING_DYNAMICS'
  | 'PREPARING_TRANSCRIPTS'
  | 'EXTRACTING'
  | 'ASSEMBLING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export interface DistillCounters {
  videos_total: number
  videos_transcribed: number
  videos_extracted: number
  videos_failed: number
  failed_bvids: string[]
}

export interface DistillRun {
  id: string
  mid: number
  up_name?: string | null
  status: DistillRunStatus
  video_limit: number
  counters: DistillCounters
  error?: string | null
  dir_path: string
  created_at: number
  updated_at: number
}

/**
 * SSE `status` 事件的负载。两种形状都可能出现（见 routes/distill.py）：
 * - 订阅后的第一条：完整快照，计数字段嵌在 `counters` 里；
 * - 之后 orchestrator 推的增量事件：只带本次变化的字段，摊平在顶层，不含 `counters`。
 */
export interface DistillStatusPayload {
  status: DistillRunStatus
  videos_total?: number
  videos_transcribed?: number
  videos_extracted?: number
  error?: string
  counters?: Partial<DistillCounters>
}

export function startDistill(mid: number, videoLimit: number) {
  return request<{ok: true; run: DistillRun}>(`/v1/up/${mid}/distill`, {
    method: 'POST',
    body: JSON.stringify({video_limit: videoLimit}),
  })
}

export function cancelDistill(runId: string) {
  return request<{ok: true}>(`/v1/distill/${runId}/cancel`, {method: 'POST'})
}

export function getDistillCorpus(runId: string) {
  return request<{ok: true; run_id: string; corpus: string}>(`/v1/distill/${runId}/corpus`)
}

export function getLatestDistillRun(mid: number) {
  return request<{ok: true; run: DistillRun | null}>(`/v1/up/${mid}/distill/latest`)
}

export function deleteDistill(mid: number) {
  return request<{ok: true}>(`/v1/up/${mid}/distill`, {method: 'DELETE'})
}

export type UpOrder = 'pubdate' | 'click'

export function getUpVideos(
  mid: number,
  params: {page?: number; keyword?: string; order?: UpOrder} = {},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  search.set('page', String(params.page ?? 1))
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.order) search.set('order', params.order)
  return request<UpVideosResponse>(`/v1/up/${mid}/videos?${search.toString()}`, init)
}

export {API_BASE_URL}
