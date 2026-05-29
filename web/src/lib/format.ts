import type {JobStatus} from './api'

const statusLabels: Record<JobStatus, string> = {
  PENDING: '等待中',
  FETCHING_META: '拉取元信息',
  DOWNLOADING_AUDIO: '下载音频',
  TRANSCRIBING: '转录中',
  TRANSCRIPT_READY: '等待确认',
  SUMMARIZING: '要約中',
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

export function formatDate(ms: number) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(ms))
}
