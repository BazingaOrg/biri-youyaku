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
  document_id?: string | null
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

export function getJob(jobId: string, init?: RequestInit & {lite?: boolean}) {
  // init 主要是为了 useJob 透传 AbortController.signal：jobId 切换时取消上一个请求，
  // 避免旧 jobId 的响应晚到覆盖新 jobId 的数据。
  const {lite, ...requestInit} = init ?? {}
  return request<{ok: true; job: Job}>(`/v1/jobs/${jobId}${lite ? '?lite=true' : ''}`, requestInit)
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

export type LibraryItemKind = 'document' | 'legacy_job'

export interface LibraryListItem {
  kind: LibraryItemKind
  id: string
  document_id?: string | null
  job_id?: string | null
  title: string
  author?: string | null
  mid?: number | null
  bvid?: string | null
  cid?: number | null
  duration?: number | null
  tags: string[]
  tldr?: string | null
  saved_at?: number | null
  source_url?: string | null
  legacy?: boolean
  legacy_reason?: string | null
}

export interface LibraryListResponse {
  ok: true
  items: LibraryListItem[]
  next_cursor?: string | null
}

export type SearchScope = 'all' | 'notes' | 'subs'

export interface LibrarySearchHit {
  kind: 'notes' | 'subs'
  chunk_ord?: number | null
  heading_path: string
  start_sec?: number | null
  end_sec?: number | null
  snippet: string
}

export interface LibrarySearchMatch {
  title: boolean
  author: boolean
  bvid: boolean
  tags: string[]
}

export interface LibrarySearchGroup {
  document_id?: string | null
  job_id?: string | null
  title: string
  author?: string | null
  mid?: number | null
  bvid?: string | null
  cid?: number | null
  source_url?: string | null
  saved_at?: number | null
  tags: string[]
  tldr?: string | null
  duration?: number | null
  legacy?: boolean
  legacy_reason?: string | null
  match: LibrarySearchMatch
  hits: LibrarySearchHit[]
  hit_counts: {notes: number; subs: number}
  more?: boolean
}

export interface LibrarySearchResponse {
  ok: true
  query: string
  scope: SearchScope
  partial: string[]
  next_cursor?: string | null
  groups: LibrarySearchGroup[]
  hit_counts?: {notes?: number; subs?: number; documents?: number} | null
}

export interface LibraryNoteChunk {
  chunk_ord: number
  heading_path: string
  start_sec?: number | null
  text: string
}

export interface LibraryTranscriptCue {
  start: number
  end: number
  text: string
  index?: number
}

export interface LibraryDocumentContent {
  document: {
    id: string
    title?: string | null
    author?: string | null
    mid?: number | null
    bvid?: string | null
    cid?: number | null
    duration?: number | null
    tags: string[]
    tldr?: string | null
    source_url?: string | null
    deleted_at?: number | null
    expires_at?: number | null
    job_id?: string | null
    legacy?: boolean
    legacy_reason?: string | null
    subtitle_source?: string | null
  }
  summary: {markdown: string; content_hash?: string | null}
  transcript: LibraryTranscriptCue[]
  note_chunks: LibraryNoteChunk[]
  transcript_chunks: Array<{
    chunk_ord?: number | null
    start_sec: number
    end_sec?: number | null
    text: string
  }>
}

export interface TrashItem {
  document_id: string
  title?: string | null
  author?: string | null
  bvid?: string | null
  deleted_at: number
  expires_at?: number | null
  days_left: number
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function asString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return fallback
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function asBool(value: unknown): boolean {
  return value === true || value === 'true' || value === 1
}

function asTags(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => asString(item).trim()).filter(Boolean)
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed: unknown = JSON.parse(value)
      if (Array.isArray(parsed)) {
        return parsed.map((item) => asString(item).trim()).filter(Boolean)
      }
    } catch {
      return value.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
    }
  }
  return []
}

function asHeadingPath(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => asString(item).trim()).filter(Boolean).join(' · ')
  }
  return asString(value)
}

function unixMaybeMs(value: number | null): number | null {
  if (value == null) return null
  return value > 0 && value < 1e12 ? value * 1000 : value
}

function normalizeLibraryItem(raw: unknown): LibraryListItem | null {
  const row = asRecord(raw)
  if (!row) return null
  const documentId = asString(row.document_id || row.id || row.documentId)
  const jobId = asString(row.job_id || row.jobId) || null
  const kind: LibraryItemKind =
    asString(row.kind) === 'legacy_job' || (asBool(row.legacy) && !documentId)
      ? 'legacy_job'
      : 'document'
  const id = kind === 'legacy_job' ? asString(jobId || row.id) : asString(documentId || row.id)
  if (!id) return null
  return {
    kind,
    id,
    document_id: documentId || null,
    job_id: jobId,
    title: asString(row.title) || asString(row.url) || '未命名',
    author: asString(row.author) || null,
    mid: asNumber(row.mid),
    bvid: asString(row.bvid || row.external_bvid) || null,
    cid: asNumber(row.cid ?? row.external_cid),
    duration: asNumber(row.duration),
    tags: asTags(row.tags ?? row.tags_json),
    tldr: asString(row.tldr) || null,
    saved_at: unixMaybeMs(asNumber(row.saved_at ?? row.updated_at ?? row.created_at ?? row.completed_at)),
    source_url: asString(row.source_url || row.url) || null,
    legacy: asBool(row.legacy) || kind === 'legacy_job',
    legacy_reason: asString(row.legacy_reason) || null,
  }
}

function normalizeSearchHit(raw: unknown): LibrarySearchHit | null {
  const row = asRecord(raw)
  if (!row) return null
  const kind = asString(row.kind || row.source_level)
  const notes = kind === 'notes' || kind === 'summary' || kind === 'note'
  return {
    kind: notes ? 'notes' : 'subs',
    chunk_ord: asNumber(row.chunk_ord ?? row.ord),
    heading_path: asHeadingPath(row.heading_path ?? row.heading),
    start_sec: asNumber(row.start_sec ?? row.start),
    end_sec: asNumber(row.end_sec ?? row.end),
    snippet: asString(row.snippet || row.text || row.body),
  }
}

function normalizeSearchMatch(raw: unknown, group: Record<string, unknown>, query: string): LibrarySearchMatch {
  const row = asRecord(raw) ?? {}
  const tags = asTags(row.tags)
  const q = query.trim().toLowerCase()
  const includes = (value: unknown) => Boolean(q && asString(value).toLowerCase().includes(q))
  return {
    title: asBool(row.title) || includes(group.title),
    author: asBool(row.author) || includes(group.author),
    bvid: 'bvid' in row ? asBool(row.bvid) : includes(group.bvid),
    tags: tags.length > 0 ? tags : asTags(group.tags).filter((tag) => includes(tag)),
  }
}

function normalizeSearchGroup(raw: unknown, query: string): LibrarySearchGroup | null {
  const row = asRecord(raw)
  if (!row) return null
  const hits = (Array.isArray(row.hits) ? row.hits : []).map(normalizeSearchHit).filter((hit): hit is LibrarySearchHit => hit != null)
  const hitCounts = asRecord(row.hit_counts)
  const notes = asNumber(hitCounts?.notes) ?? hits.filter((hit) => hit.kind === 'notes').length
  const subs = asNumber(hitCounts?.subs) ?? hits.filter((hit) => hit.kind === 'subs').length
  return {
    document_id: asString(row.document_id) || null,
    job_id: asString(row.job_id) || null,
    title: asString(row.title) || '未命名',
    author: asString(row.author) || null,
    mid: asNumber(row.mid),
    bvid: asString(row.bvid) || null,
    cid: asNumber(row.cid),
    source_url: asString(row.source_url) || null,
    saved_at: unixMaybeMs(asNumber(row.saved_at ?? row.updated_at ?? row.created_at)),
    tags: asTags(row.tags ?? row.tags_json),
    tldr: asString(row.tldr) || null,
    duration: asNumber(row.duration),
    legacy: asBool(row.legacy),
    legacy_reason: asString(row.legacy_reason) || null,
    match: normalizeSearchMatch(row.match, row, query),
    hits,
    hit_counts: {notes, subs},
    more: asBool(row.more),
  }
}

function normalizeCue(raw: unknown, index: number): LibraryTranscriptCue | null {
  const row = asRecord(raw)
  if (!row) return null
  const text = asString(row.text)
  const start = asNumber(row.start ?? row.start_sec) ?? 0
  const end = asNumber(row.end ?? row.end_sec) ?? start
  if (!text && start === 0) return null
  return {start, end, text, index}
}

function normalizeNoteChunk(raw: unknown, index: number): LibraryNoteChunk | null {
  const row = asRecord(raw)
  if (!row) return null
  const text = asString(row.text || row.body || row.markdown || row.snippet)
  return {
    chunk_ord: asNumber(row.chunk_ord ?? row.ord) ?? index,
    heading_path: asHeadingPath(row.heading_path ?? row.heading),
    start_sec: asNumber(row.start_sec ?? row.start),
    text,
  }
}

export function normalizeLibraryDocumentContent(raw: unknown): LibraryDocumentContent {
  const root = asRecord(raw) ?? {}
  const payload = asRecord(root.document) ? root : {document: root, ...root}
  const document = asRecord(payload.document) ?? payload
  const summaryRaw = asRecord(payload.summary) ?? {}
  const markdown = asString(
    summaryRaw.markdown || summaryRaw.text || payload.markdown || payload.summary_markdown || payload.summary,
  )
  const cuesSource =
    (Array.isArray(payload.transcript) ? payload.transcript : null) ??
    (Array.isArray(asRecord(payload.transcript)?.cues) ? (asRecord(payload.transcript)?.cues as unknown[]) : null) ??
    (Array.isArray(payload.cues) ? payload.cues : [])
  const noteSource =
    (Array.isArray(payload.note_chunks) ? payload.note_chunks : null) ??
    (Array.isArray(payload.rag_chunks) ? payload.rag_chunks : null) ??
    (Array.isArray(payload.chunks) ? payload.chunks : [])
  const transcriptChunksSource = Array.isArray(payload.transcript_chunks) ? payload.transcript_chunks : []
  return {
    document: {
      id: asString(document.id || document.document_id || payload.id),
      title: asString(document.title) || null,
      author: asString(document.author) || null,
      mid: asNumber(document.mid),
      bvid: asString(document.bvid || document.external_bvid) || null,
      cid: asNumber(document.cid ?? document.external_cid),
      duration: asNumber(document.duration),
      tags: asTags(document.tags ?? document.tags_json),
      tldr: asString(document.tldr) || null,
      source_url: asString(document.source_url || document.url) || null,
      deleted_at: unixMaybeMs(asNumber(document.deleted_at)),
      expires_at: unixMaybeMs(asNumber(document.expires_at)),
      job_id: asString(document.job_id || payload.job_id) || null,
      legacy: asBool(document.legacy),
      legacy_reason: asString(document.legacy_reason) || null,
      subtitle_source: asString(document.subtitle_source) || null,
    },
    summary: {
      markdown,
      content_hash: asString(summaryRaw.content_hash || payload.content_hash || document.content_hash) || null,
    },
    transcript: cuesSource.map(normalizeCue).filter((cue): cue is LibraryTranscriptCue => cue != null),
    note_chunks: noteSource.map(normalizeNoteChunk).filter((chunk): chunk is LibraryNoteChunk => chunk != null),
    transcript_chunks: transcriptChunksSource.map((item, index) => {
      const row = asRecord(item) ?? {}
      return {
        chunk_ord: asNumber(row.chunk_ord ?? row.ord) ?? index,
        start_sec: asNumber(row.start_sec ?? row.start) ?? 0,
        end_sec: asNumber(row.end_sec ?? row.end),
        text: asString(row.text || row.body || row.snippet),
      }
    }),
  }
}

function normalizeTrashItem(raw: unknown): TrashItem | null {
  const row = asRecord(raw)
  if (!row) return null
  const documentId = asString(row.document_id || row.id)
  if (!documentId) return null
  const deletedAt = unixMaybeMs(asNumber(row.deleted_at)) ?? 0
  const expiresAt = unixMaybeMs(asNumber(row.expires_at))
  const daysLeft =
    asNumber(row.days_left) ??
    (expiresAt != null ? Math.max(0, Math.ceil((expiresAt - Date.now()) / 86_400_000)) : 0)
  return {
    document_id: documentId,
    title: asString(row.title) || null,
    author: asString(row.author) || null,
    bvid: asString(row.bvid || row.external_bvid) || null,
    deleted_at: deletedAt,
    expires_at: expiresAt,
    days_left: daysLeft,
  }
}

export function listLibrary(
  params: {cursor?: string | null; up?: string; tag?: string; limit?: number} = {},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  if (params.limit) search.set('limit', String(params.limit))
  if (params.cursor) search.set('cursor', params.cursor)
  if (params.up) search.set('up', params.up)
  if (params.tag) search.set('tag', params.tag)
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request<Record<string, unknown>>(`/v1/library${suffix}`, init).then((payload) => {
    const itemsRaw = Array.isArray(payload.items)
      ? payload.items
      : Array.isArray(payload.documents)
        ? payload.documents
        : Array.isArray(payload.results)
          ? payload.results
          : []
    return {
      ok: true as const,
      items: itemsRaw.map(normalizeLibraryItem).filter((item): item is LibraryListItem => item != null),
      next_cursor: asString(payload.next_cursor) || null,
    }
  })
}

export function searchLibrary(
  params: {q: string; scope?: SearchScope; cursor?: string | null; limit?: number},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  search.set('q', params.q)
  if (params.scope) search.set('scope', params.scope)
  if (params.cursor) search.set('cursor', params.cursor)
  if (params.limit) search.set('limit', String(params.limit))
  return request<Record<string, unknown>>(`/v1/library/search?${search.toString()}`, init).then((payload) => {
    const query = asString(payload.query, params.q)
    const groupsRaw = Array.isArray(payload.groups) ? payload.groups : Array.isArray(payload.results) ? payload.results : []
    const partial = Array.isArray(payload.partial) ? payload.partial.map((item) => asString(item)).filter(Boolean) : []
    const hitCounts = asRecord(payload.hit_counts)
    return {
      ok: true as const,
      query,
      scope: (asString(payload.scope, params.scope ?? 'all') as SearchScope) || 'all',
      partial,
      next_cursor: asString(payload.next_cursor) || null,
      groups: groupsRaw.map((row) => normalizeSearchGroup(row, query)).filter((row): row is LibrarySearchGroup => row != null),
      hit_counts: hitCounts
        ? {
            notes: asNumber(hitCounts.notes) ?? undefined,
            subs: asNumber(hitCounts.subs) ?? undefined,
            documents: asNumber(hitCounts.documents) ?? undefined,
          }
        : null,
    }
  })
}

const documentContentCache = new Map<string, {etag: string; body: LibraryDocumentContent}>()

export async function getLibraryDocumentContent(id: string, init?: RequestInit): Promise<LibraryDocumentContent> {
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json')
  const token = getApiToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const cached = documentContentCache.get(id)
  if (cached?.etag) headers.set('If-None-Match', cached.etag)

  const url = `${API_BASE_URL}/v1/library/documents/${encodeURIComponent(id)}/content`
  let response: Response
  try {
    response = await fetch(url, {...init, headers, credentials: init?.credentials ?? 'include'})
  } catch (error) {
    if (!(error instanceof TypeError) || init?.signal?.aborted) throw error
    await new Promise((resolve) => window.setTimeout(resolve, 500))
    response = await fetch(url, {...init, headers, credentials: init?.credentials ?? 'include'})
  }
  if (response.status === 304) {
    if (cached) return cached.body
    headers.delete('If-None-Match')
    response = await fetch(url, {...init, headers, credentials: init?.credentials ?? 'include'})
  }
  if (!response.ok) {
    throw new ApiError(response.status, (await getErrorMessage(response)) || `HTTP ${response.status}`)
  }
  const payload: unknown = await response.json()
  const body = normalizeLibraryDocumentContent(payload)
  const etag = response.headers.get('ETag') || body.summary.content_hash || ''
  if (etag) documentContentCache.set(id, {etag, body})
  return body
}

export function listLibraryTrash(init?: RequestInit) {
  return request<Record<string, unknown>>('/v1/library/trash', init).then((payload) => {
    const itemsRaw = Array.isArray(payload.items) ? payload.items : Array.isArray(payload.documents) ? payload.documents : []
    return {
      ok: true as const,
      items: itemsRaw.map(normalizeTrashItem).filter((item): item is TrashItem => item != null),
    }
  })
}

export function softDeleteDocument(documentId: string) {
  return request<{ok: true}>(`/v1/knowledge/documents/${encodeURIComponent(documentId)}/soft-delete`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function restoreDocument(documentId: string) {
  return request<{ok: true}>(`/v1/knowledge/documents/${encodeURIComponent(documentId)}/restore`, {
    method: 'POST',
  })
}

export function purgeDocument(documentId: string, confirmTitle: string) {
  return request<{ok: true}>(`/v1/knowledge/documents/${encodeURIComponent(documentId)}/purge`, {
    method: 'POST',
    body: JSON.stringify({confirm: true, confirm_title: confirmTitle}),
  })
}

export function biliPlayUrl(sourceUrl?: string | null, bvid?: string | null, startSec?: number | null) {
  const base = sourceUrl || (bvid ? `https://www.bilibili.com/video/${bvid}` : null)
  if (!base) return null
  if (startSec == null || Number.isNaN(startSec)) return base
  try {
    const url = new URL(base)
    url.searchParams.set('t', String(Math.floor(startSec)))
    return url.toString()
  } catch {
    return `${base}${base.includes('?') ? '&' : '?'}t=${Math.floor(startSec)}`
  }
}

export {API_BASE_URL}
