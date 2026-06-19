import type {ReactNode} from 'react'
import ReactMarkdown from 'react-markdown'
import type {Job, JobStatus} from '../../lib/api'
import type {StepDef, StepState} from '../../components/StepCarousel'
import {formatDuration} from '../../lib/format'

/** status → 步骤索引（识别 / 字幕 / 总结 / 邮件）。终态映射到 0 让失败卡片继续在 0 上展示。 */
export function statusToStepIndex(status: JobStatus): number {
  switch (status) {
    case 'PENDING':
    case 'FETCHING_META':
      return 0
    case 'DOWNLOADING_AUDIO':
    case 'TRANSCRIBING':
    case 'TRANSCRIPT_READY':
      return 1
    case 'SUMMARIZING':
      return 2
    case 'EMAILING':
      return 3
    case 'COMPLETED':
      return 4
    case 'FAILED':
    case 'CANCELED':
      return 0
    default:
      return 0
  }
}

function pickStepState(idx: number, currentIdx: number, status: JobStatus): StepState {
  if (status === 'FAILED' || status === 'CANCELED') {
    if (idx === currentIdx) return 'failed'
    if (idx < currentIdx) return 'done'
    return 'pending'
  }
  if (idx < currentIdx) return 'done'
  if (idx === currentIdx) return 'active'
  return 'pending'
}

export function buildSteps(job: Job): StepDef[] {
  const status = job.status
  const currentIdx = statusToStepIndex(status)
  const emailEnabled = job.options.email_enabled
  const indices = emailEnabled ? [0, 1, 2, 3] : [0, 1, 2]
  const labels: Record<number, string> = {
    0: '识别视频',
    1: job.subtitle_source === 'platform' ? '字幕' : '字幕 / 转写',
    2: '总结',
    3: '邮件',
  }
  return indices.map((idx) => ({
    key: String(idx),
    label: labels[idx],
    state: pickStepState(idx, currentIdx, status),
    render: () => renderStep(idx, job),
  }))
}

function renderStep(idx: number, job: Job): ReactNode {
  if (idx === 0) return renderMeta(job)
  if (idx === 1) return renderSubtitle(job)
  if (idx === 2) return renderSummary(job)
  if (idx === 3) return renderEmail(job)
  return null
}

function renderMeta(job: Job) {
  if (job.bvid) {
    return (
      <div className="grid gap-1">
        <p className="break-words text-ink">{job.title || '已识别'}</p>
        <p className="text-xs">
          {job.author || '未知 UP'} · {formatDuration(job.duration)}
        </p>
      </div>
    )
  }
  if (job.status === 'FETCHING_META') return <p>识别中…</p>
  return <p>等待识别视频</p>
}

function renderSubtitle(job: Job) {
  if (job.subtitle_source === 'platform') {
    return (
      <div className="grid gap-2">
        <p className="text-ink">找到官方字幕</p>
        {job.transcript.slice(0, 3).map((line, i) => (
          <p key={i} className="text-xs break-words">· {line.text}</p>
        ))}
      </div>
    )
  }
  if (job.status === 'DOWNLOADING_AUDIO') {
    if (job.queued) return <p>排队中…（等下载槽位）</p>
    const pct = Math.round(job.download_progress?.percent ?? 0)
    return (
      <div className="grid gap-2">
        <p>下载音频 {pct}%</p>
        <div className="h-2 overflow-hidden rounded-full bg-panel">
          <div
            className="h-full rounded-full bg-brand transition-[width] duration-200"
            style={{width: `${pct}%`}}
          />
        </div>
      </div>
    )
  }
  if (job.status === 'TRANSCRIBING') {
    if (job.queued) return <p>排队中…（等转写槽位）</p>
    const pct = Math.round((job.transcribe_progress?.percent ?? 0))
    const itemsCount = job.transcribe_progress?.items_count ?? job.transcript.length
    const preview = job.transcribe_progress?.preview
    return (
      <div className="grid gap-2">
        <p>语音转写中 {pct}%</p>
        <div className="h-2 overflow-hidden rounded-full bg-panel">
          <div
            className="h-full rounded-full bg-brand transition-[width] duration-200"
            style={{width: `${pct}%`}}
          />
        </div>
        {itemsCount > 0 && <p className="text-xs">已识别 {itemsCount} 段</p>}
        {preview && <p className="break-words text-xs text-ink/80">…{preview}</p>}
      </div>
    )
  }
  if (job.status === 'TRANSCRIPT_READY' || job.transcript.length > 0) {
    return (
      <div className="grid gap-2">
        <p className="text-ink">字幕已就绪</p>
        {job.transcript.slice(0, 3).map((line, i) => (
          <p key={i} className="text-xs break-words">· {line.text}</p>
        ))}
      </div>
    )
  }
  return <p>等待字幕</p>
}

function renderSummary(job: Job) {
  if (job.summary) {
    return (
      <div className="prose prose-sm max-h-48 max-w-none overflow-y-auto break-words text-ink dark:prose-invert prose-a:text-brand [&_pre]:overflow-x-auto [&_table]:block [&_table]:overflow-x-auto [&_code]:break-all">
        <ReactMarkdown>{job.summary}</ReactMarkdown>
      </div>
    )
  }
  if (job.status === 'SUMMARIZING') {
    if (job.queued) return <p>排队中…（等总结槽位）</p>
    // 长视频分段总结阶段没有流式 token，用段进度兜住「正在生成总结」的空窗。
    const seg = job.summary_segment
    if (seg && seg.total > 1 && seg.done < seg.total) {
      const pct = Math.round((seg.done / seg.total) * 100)
      return (
        <div className="grid gap-2">
          <p>分段总结中 {seg.done}/{seg.total}</p>
          <div className="h-2 overflow-hidden rounded-full bg-panel">
            <div
              className="h-full rounded-full bg-brand transition-[width] duration-200"
              style={{width: `${pct}%`}}
            />
          </div>
          <p className="text-xs">分段完成后再合并成完整笔记…</p>
        </div>
      )
    }
    return <p>正在生成总结…</p>
  }
  return <p>等待生成总结</p>
}

function renderEmail(job: Job) {
  if (job.status === 'COMPLETED') return <p className="text-ink">已发送到邮箱</p>
  if (job.status === 'EMAILING') return <p>发送中…</p>
  return <p>完成后自动发送</p>
}
