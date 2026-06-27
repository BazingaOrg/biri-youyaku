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
}

let cached: Promise<RuntimeConfig> | null = null

export function loadRuntimeConfig(): Promise<RuntimeConfig> {
  if (cached) return cached
  cached = getRuntimeConfig().catch(() => FALLBACK)
  return cached
}

/** 强制下次重新拉。一般用不到，留给开发期手动刷新。 */
export function resetRuntimeConfig(): void {
  cached = null
}
