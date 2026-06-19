import type {Job, JobStatus} from './api'

const statusLabels: Record<JobStatus, string> = {
  PENDING: '等待中',
  FETCHING_META: '识别视频',
  DOWNLOADING_AUDIO: '下载音频',
  TRANSCRIBING: '语音转写',
  TRANSCRIPT_READY: '等待继续',
  SUMMARIZING: '生成总结',
  EMAILING: '发送邮件',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELED: '已取消',
}

export function formatStatus(status: JobStatus) {
  return statusLabels[status]
}

export function formatDuration(seconds?: number) {
  if (seconds == null || Number.isNaN(seconds)) {
    return '--:--'
  }
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  if (mins >= 60) {
    const hours = Math.floor(mins / 60)
    return `${hours}:${String(mins % 60).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${mins}:${String(secs).padStart(2, '0')}`
}

const STAGE_LABELS: Record<string, string> = {
  FETCHING_META: '识别',
  DOWNLOADING_AUDIO: '下载',
  TRANSCRIBING: '转写',
  SUMMARIZING: '总结',
  EMAILING: '邮件',
}

/** 把 stage_timings 渲染成「转写 12.3s · 总结 8.1s」。无有效数据返回空串。 */
export function formatStageTimings(timings: Job['stage_timings']): string {
  return (timings ?? [])
    .filter((t) => t.duration_ms > 0 && STAGE_LABELS[t.stage])
    .map((t) => `${STAGE_LABELS[t.stage]} ${(t.duration_ms / 1000).toFixed(1)}s`)
    .join(' · ')
}

// 各模型粗略单价（¥ / 1M tokens），仅用于「让自己烧的钱有感」，不保证实时准确。
// 命中靠模型名子串匹配；未命中返回 null（不显示成本，避免给出错误金额）。
const MODEL_PRICING: Array<{match: RegExp; input: number; output: number}> = [
  {match: /deepseek/i, input: 1, output: 2},
]

export function estimateCostCny(
  tokenUsage: Record<string, unknown> | undefined,
  model: string | undefined,
): number | null {
  if (!tokenUsage) return null
  const input = Number(tokenUsage.input_tokens) || 0
  const output = Number(tokenUsage.output_tokens) || 0
  if (input === 0 && output === 0) return null
  const price = MODEL_PRICING.find((p) => model != null && p.match.test(model))
  if (!price) return null
  return (input / 1_000_000) * price.input + (output / 1_000_000) * price.output
}

export function formatTokenCount(tokenUsage: Record<string, unknown> | undefined): string | null {
  const total = Number(tokenUsage?.total_tokens) || 0
  if (total === 0) return null
  if (total >= 1000) return `${(total / 1000).toFixed(1)}k tokens`
  return `${total} tokens`
}

export function formatDate(ms: number) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(ms))
}
