import {Captions, Clock, Copy, FileDown, History, Mail, Music, Plus, RotateCw, Tag} from 'lucide-react'
import type {Job} from '../../lib/api'
import {formatStageTimings, formatTokenCount} from '../../lib/format'
import {IconButton} from '../../components/IconButton'
import {MetaBar} from './MetaBar'
import {SummaryTabs} from './SummaryTabs'

function JobStats({job}: {job: Job}) {
  const timings = formatStageTimings(job.stage_timings)
  const tokens = formatTokenCount(job.token_usage)
  const parts = [timings, tokens].filter(Boolean)
  if (parts.length === 0) return null
  return (
    <div className="inline-flex max-w-full items-center gap-1.5 overflow-hidden px-1 text-xs text-muted">
      <Clock size={12} className="shrink-0" />
      <span className="min-w-0 whitespace-nowrap">{parts.join(' · ')}</span>
    </div>
  )
}

function TagChips({tags}: {tags?: string[]}) {
  if (!tags || tags.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-1">
      <Tag size={12} className="shrink-0 text-muted" />
      {tags.map((tag) => (
        <span key={tag} className="rounded-full bg-brandSoft px-2 py-0.5 text-xs text-brand">
          {tag}
        </span>
      ))}
    </div>
  )
}

interface DoneViewProps {
  job: Job
  onNew: () => void
  onOpenHistory: () => void
  onDownloadAudio: () => void
  onCopy: () => void
  onDownloadMarkdown: () => void
  onDownloadSubtitle: () => void
  onResendEmail: () => void
  emailBusy: boolean
}

export function DoneView({
  job,
  onNew,
  onOpenHistory,
  onDownloadAudio,
  onCopy,
  onDownloadMarkdown,
  onDownloadSubtitle,
  onResendEmail,
  emailBusy,
}: DoneViewProps) {
  return (
    <div className="grid min-w-0 gap-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <IconButton icon={<Plus size={18} />} label="新建" onClick={onNew} />
        <IconButton
          icon={<Music size={18} />}
          label="下载音频"
          onClick={onDownloadAudio}
          disabled={!job.audio_available}
        />
        <IconButton icon={<Copy size={18} />} label="复制总结" onClick={onCopy} disabled={!job.summary} />
        <IconButton
          icon={<FileDown size={18} />}
          label="下载 Markdown"
          onClick={onDownloadMarkdown}
          disabled={!job.summary}
        />
        <IconButton
          icon={<Captions size={18} />}
          label="下载字幕"
          onClick={onDownloadSubtitle}
          disabled={!job.transcript?.length}
        />
        <IconButton icon={<History size={18} />} label="历史" onClick={onOpenHistory} />
      </div>
      <MetaBar job={job} />
      <JobStats job={job} />
      <TagChips tags={job.tags} />
      {job.email_error && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          <p className="break-words leading-6">总结已完成，邮件未送达：{job.email_error}</p>
          <button
            type="button"
            onClick={onResendEmail}
            disabled={emailBusy}
            className="inline-flex items-center gap-1 rounded-xl border border-warning/30 px-2 py-1 text-xs text-warning transition hover:bg-warning/20 disabled:opacity-60"
          >
            {emailBusy ? <RotateCw size={12} className="animate-spin" /> : <Mail size={12} />}
            重发邮件
          </button>
        </div>
      )}
      <SummaryTabs job={job} />
    </div>
  )
}
