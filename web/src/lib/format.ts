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

function formatElapsedMs(ms: number): string {
  if (ms < 1000) return '<1s'
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  if (minutes < 60) return rest > 0 ? `${minutes}m ${rest}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}

/** 把 stage_timings 聚合成「累计 45s」。逐段明细太长，重试后还会重复展开。 */
export function formatStageTimings(timings: Job['stage_timings']): string {
  const totalMs = (timings ?? []).reduce((sum, timing) => {
    const duration = Number(timing.duration_ms) || 0
    return duration > 0 ? sum + duration : sum
  }, 0)
  return totalMs > 0 ? `累计 ${formatElapsedMs(totalMs)}` : ''
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

/** 仅年月日：UP 投稿列表跨越多年，需要带年份。 */
export function formatDay(ms: number) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(ms))
}
