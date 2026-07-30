/**
 * 运行时能力探测：调一次 `/v1/config/runtime`，全 app 共享结果。
 *
 * - 用 module-level promise 缓存，组件多次 import 不会重复请求。
 * - 拉失败时（后端没起、CF Access 弹 SSO 等）兜底成「能力都没配」，让 UI 走保守分支。
 */
import {getRuntimeConfig, type RuntimeConfig} from './api'

const FALLBACK: RuntimeConfig = {
  ok: true,
  auth_mode: 'none',
  llm_configured: false,
  email_configured: false,
  bilibili_cookie_configured: false,
  // 不在 fallback 里写 knowledge_* = false：否则 KnowledgePage 里
  // `runtime?.knowledge_chat_enabled ?? status?.chat_enabled` 会因 false 不触发 ??，
  // 把 /v1/knowledge/status 已返回的 chat_enabled=true 盖掉，切换按钮永远不出现。
}

let cached: Promise<RuntimeConfig> | null = null

export function loadRuntimeConfig(): Promise<RuntimeConfig> {
  if (cached) return cached
  cached = getRuntimeConfig().catch(() => FALLBACK)
  return cached
}

/** Drop cache so knowledge chat / search flags re-fetch after .env + backend restart. */
export function clearRuntimeConfigCache(): void {
  cached = null
}

/** Always hit the network (used by KnowledgePage so ask-toggle is not stuck false). */
export function reloadRuntimeConfig(): Promise<RuntimeConfig> {
  clearRuntimeConfigCache()
  return loadRuntimeConfig()
}

