import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {Download, ExternalLink, History, Plus, RotateCw, XCircle} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import {useLocation} from 'wouter'
import {cancelJob, createJob, downloadJobAudio, getJob, resumeJob, retryJob} from '../lib/api'
import type {Job, JobStatus} from '../lib/api'
import {isValidBiliUrl} from '../lib/url'
import {formatDuration} from '../lib/format'
import {friendlyError} from '../lib/errorMap'
import {useJob} from '../hooks/useJob'
import {useJobStream} from '../hooks/useJobStream'
import {useToast} from '../components/ToastProvider'
import {UrlInput} from '../components/UrlInput'
import {StepCarousel, type StepDef, type StepState} from '../components/StepCarousel'
import {HistoryDrawer} from '../components/HistoryDrawer'
import {clearActive, readActive, subscribeActive, writeActive} from '../lib/activeJob'

interface WorkspaceProps {
  jobId: string | null
}

const RUNNING_STATUSES: JobStatus[] = [
  'PENDING',
  'FETCHING_META',
  'DOWNLOADING_AUDIO',
  'TRANSCRIBING',
  'TRANSCRIPT_READY',
  'SUMMARIZING',
  'EMAILING',
]

// ---------- 工具 ----------

function statusToStepIndex(status: JobStatus): number {
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

// ---------- 公用按钮样式 ----------

const PRIMARY_BTN =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-brand px-5 text-sm font-semibold text-white transition hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50'
const GHOST_BTN =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-lift px-4 text-sm font-medium text-muted transition hover:bg-line/70 hover:text-ink active:scale-95 disabled:cursor-not-allowed disabled:opacity-40'

// ---------- A. Idle ----------

function IdleView({
  onSubmit,
  onOpenHistory,
}: {
  onSubmit: (url: string) => Promise<void>
  onOpenHistory: () => void
}) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!isValidBiliUrl(url)) {
      setError('请输入有效的 B 站视频链接')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit(url.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : '没能开始，换个链接试试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-[70vh] place-items-center">
      <div className="grid w-full max-w-xl gap-5">
        <p className="text-center text-sm leading-6 text-muted sm:text-base">
          粘贴 B 站链接，自动总结并发邮箱
        </p>
        <UrlInput
          value={url}
          loading={busy}
          error={error}
          onChange={(next) => {
            setUrl(next)
            setError(null)
          }}
          onSubmit={submit}
        />
        <div className="flex flex-wrap items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || url.trim().length === 0}
            className={PRIMARY_BTN + ' min-w-[120px]'}
          >
            {busy ? '处理中…' : '开始总结'}
          </button>
          <button type="button" onClick={onOpenHistory} className={GHOST_BTN}>
            <History size={16} />
            历史
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------- Meta & 步骤卡内容 ----------

function MetaBar({job}: {job: Job}) {
  return (
    <div className="grid gap-2 rounded-2xl bg-lift px-4 py-3 sm:px-5 sm:py-4">
      <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted">
        <span className="rounded-full bg-brandSoft px-2.5 py-1 text-brand">{job.bvid || '识别中'}</span>
        <span>
          {job.subtitle_source === 'platform'
            ? '官方字幕'
            : job.subtitle_source === 'asr'
              ? '语音转写'
              : '字幕未定'}
        </span>
        <span>{formatDuration(job.duration)}</span>
        <a
          href={job.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-muted hover:text-ink"
        >
          视频源 <ExternalLink size={12} />
        </a>
      </div>
      <p className="line-clamp-2 break-words text-base font-semibold leading-snug text-ink">
        {job.title || '识别中…'}
      </p>
      <p className="truncate text-xs text-muted">{job.author || '未知 UP'}</p>
    </div>
  )
}

function buildSteps(job: Job): StepDef[] {
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
    return (
      <div className="grid gap-1">
        <p>语音转写中…</p>
        {job.transcript.length > 0 && <p className="text-xs">已识别 {job.transcript.length} 段</p>}
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
      <div className="prose prose-sm max-h-48 max-w-none overflow-y-auto break-words text-ink prose-a:text-brand">
        <ReactMarkdown>{job.summary}</ReactMarkdown>
      </div>
    )
  }
  if (job.status === 'SUMMARIZING')
    return (
      <p>
        正在生成总结… 模型 <span className="break-all text-ink">{job.options.llm_model}</span>
      </p>
    )
  return <p>等待生成总结</p>
}

function renderEmail(job: Job) {
  if (job.status === 'COMPLETED') return <p className="text-ink">已发送到邮箱</p>
  if (job.status === 'EMAILING') return <p>发送中…</p>
  return <p>完成后自动发送</p>
}

// ---------- B. Running ----------

function RunningView({
  job,
  onCancel,
  onRetry,
  onNew,
  onOpenHistory,
  busy,
}: {
  job: Job
  onCancel: () => void
  onRetry: () => void
  onNew: () => void
  onOpenHistory: () => void
  busy: boolean
}) {
  const steps = useMemo(() => buildSteps(job), [job])
  const currentIdx = statusToStepIndex(job.status)
  const failure = job.error_message ? friendlyError(job.error_code, job.error_message) : null
  const canCancel = RUNNING_STATUSES.includes(job.status)
  const canRetry = job.status === 'FAILED'

  return (
    <div className="grid gap-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
        <button type="button" onClick={onNew} className={GHOST_BTN}>
          <Plus size={16} /> 新建
        </button>
        <button type="button" onClick={onOpenHistory} className={GHOST_BTN}>
          <History size={16} /> 历史
        </button>
      </div>
      <MetaBar job={job} />
      <StepCarousel steps={steps} currentIndex={currentIdx} />
      {failure && (
        <div className="rounded-2xl border border-danger/30 bg-red-50/60 p-4 text-sm text-danger">
          <p className="font-semibold">{failure.title}</p>
          <p className="mt-1 break-words leading-6">{failure.message}</p>
        </div>
      )}
      {(canCancel || canRetry) && (
        <div className="flex flex-wrap items-center justify-center gap-2">
          {canCancel && (
            <button type="button" onClick={onCancel} className={GHOST_BTN}>
              <XCircle size={16} /> 取消
            </button>
          )}
          {canRetry && (
            <button type="button" onClick={onRetry} disabled={busy} className={PRIMARY_BTN}>
              <RotateCw size={16} /> {failure?.actionLabel || '重试'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ---------- C. Done ----------

function DoneView({
  job,
  onNew,
  onOpenHistory,
  onDownloadAudio,
  onCopy,
  onDownloadMarkdown,
}: {
  job: Job
  onNew: () => void
  onOpenHistory: () => void
  onDownloadAudio: () => void
  onCopy: () => void
  onDownloadMarkdown: () => void
}) {
  return (
    <div className="grid gap-4 py-4">
      <MetaBar job={job} />
      <section className="rounded-3xl bg-panel p-4 shadow-card sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-[-0.012em]">视频总结</h2>
          <span className="truncate text-xs text-muted">{job.options.llm_model}</span>
        </div>
        {job.summary ? (
          <div className="prose prose-sm max-w-none break-words text-ink prose-headings:tracking-[-0.012em] prose-a:text-brand">
            <ReactMarkdown>{job.summary}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-muted">没有总结内容</p>
        )}
      </section>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <button type="button" onClick={onNew} className={GHOST_BTN}>
          <Plus size={16} /> 新建
        </button>
        <button
          type="button"
          onClick={onDownloadAudio}
          disabled={!job.audio_available}
          className={GHOST_BTN}
        >
          <Download size={16} /> 下载音频
        </button>
        <button type="button" onClick={onCopy} disabled={!job.summary} className={GHOST_BTN}>
          复制
        </button>
        <button
          type="button"
          onClick={onDownloadMarkdown}
          disabled={!job.summary}
          className={GHOST_BTN}
        >
          下载 .md
        </button>
        <button type="button" onClick={onOpenHistory} className={GHOST_BTN}>
          <History size={16} /> 历史
        </button>
      </div>
    </div>
  )
}

// ---------- Workspace shell ----------

export function Workspace({jobId}: WorkspaceProps) {
  const [, navigate] = useLocation()
  const toast = useToast()
  const {job, setJob, error, refresh} = useJob(jobId)
  const [actionBusy, setActionBusy] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const autoResumedRef = useRef<string | null>(null)
  const notifiedRef = useRef<string | null>(null)

  const patchJob = useCallback(
    (partial: Partial<Job>) => {
      setJob((current) => (current ? {...current, ...partial} : current))
    },
    [setJob],
  )
  useJobStream(jobId, patchJob)

  // 切换任务时重置一次性 flag
  useEffect(() => {
    autoResumedRef.current = null
    notifiedRef.current = null
  }, [jobId])

  // TRANSCRIPT_READY 自动 resume —— 不再二次确认
  useEffect(() => {
    if (!job || !jobId) return
    if (job.status !== 'TRANSCRIPT_READY') return
    if (autoResumedRef.current === jobId) return
    autoResumedRef.current = jobId
    void resumeJob(jobId)
      .then(() => refresh())
      .catch((err) => {
        const message = err instanceof Error ? err.message : '继续处理失败'
        toast.error('继续处理失败', message)
      })
  }, [job, jobId, refresh, toast])

  // 终态 toast 与 localStorage 清理（每个 status 只触发一次）
  useEffect(() => {
    if (!job || !jobId) return
    const key = `${jobId}:${job.status}`
    if (notifiedRef.current === key) return
    if (job.status === 'COMPLETED') {
      notifiedRef.current = key
      clearActive(jobId)
      toast.success('总结完成', job.options.email_enabled ? '已发送到邮箱' : '已生成')
    }
    if (job.status === 'FAILED' && job.error_message) {
      notifiedRef.current = key
      clearActive(jobId)
      const fe = friendlyError(job.error_code, job.error_message)
      toast.error(fe.title, fe.message)
    }
    if (job.status === 'CANCELED') {
      notifiedRef.current = key
      clearActive(jobId)
    }
  }, [job, jobId, toast])

  // 状态恢复：进入 / 路由时若有未完成 active，直接 redirect
  const [recovering, setRecovering] = useState(jobId == null && readActive() != null)
  useEffect(() => {
    if (jobId != null) return
    const pointer = readActive()
    if (!pointer) {
      setRecovering(false)
      return
    }
    let canceled = false
    setRecovering(true)
    getJob(pointer.jobId)
      .then((response) => {
        if (canceled) return
        const status = response.job.status
        if (RUNNING_STATUSES.includes(status)) {
          navigate(`/jobs/${pointer.jobId}`)
        } else {
          clearActive(pointer.jobId)
          setRecovering(false)
        }
      })
      .catch(() => {
        if (canceled) return
        clearActive(pointer.jobId)
        setRecovering(false)
      })
    return () => {
      canceled = true
    }
  }, [jobId, navigate])

  // 跨标签同步
  useEffect(() => {
    return subscribeActive((pointer) => {
      if (pointer && jobId == null) {
        navigate(`/jobs/${pointer.jobId}`)
      }
    })
  }, [jobId, navigate])

  // ---------- actions ----------

  const submitNew = async (url: string) => {
    const response = await createJob(url, {task_type: 'summary', email_enabled: true})
    writeActive({jobId: response.job_id, url})
    toast.success('已开始')
    navigate(`/jobs/${response.job_id}`)
  }

  const cancel = async () => {
    if (!jobId) return
    setActionBusy(true)
    try {
      await cancelJob(jobId)
      await refresh()
      toast.info('已取消')
    } catch (err) {
      toast.error('取消失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setActionBusy(false)
    }
  }

  const retry = async () => {
    if (!jobId) return
    setActionBusy(true)
    try {
      await retryJob(jobId)
      await refresh()
      toast.info('已重试')
    } catch (err) {
      toast.error('重试失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setActionBusy(false)
    }
  }

  const downloadAudio = async () => {
    if (!jobId) return
    try {
      const {blob, filename} = await downloadJobAudio(jobId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename || `${job?.title || jobId}.wav`
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success('音频已下载')
    } catch (err) {
      toast.error('下载音频失败', err instanceof Error ? err.message : '请重试')
    }
  }

  const copySummary = async () => {
    if (!job?.summary) return
    try {
      await navigator.clipboard.writeText(job.summary)
      toast.success('已复制')
    } catch {
      toast.error('复制失败', '请手动选中复制')
    }
  }

  const downloadMarkdown = () => {
    if (!job?.summary) return
    const blob = new Blob([job.summary], {type: 'text/markdown;charset=utf-8'})
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${job.title || 'summary'}.md`
    anchor.click()
    URL.revokeObjectURL(url)
    toast.success('Markdown 已下载')
  }

  const goNew = () => {
    clearActive()
    navigate('/')
  }
  const openHistory = () => setHistoryOpen(true)
  const closeHistory = () => setHistoryOpen(false)

  // ---------- render ----------

  const drawer = (
    <HistoryDrawer
      open={historyOpen}
      onClose={closeHistory}
      onOpenJob={(id) => navigate(`/jobs/${id}`)}
      onDeleted={(id) => {
        if (id === jobId) clearActive(id)
        toast.success('已删除')
      }}
      refreshKey={jobId ?? job?.status ?? null}
    />
  )

  if (!jobId) {
    if (recovering) {
      return (
        <>
          <p className="py-12 text-center text-sm text-muted">恢复上次任务…</p>
          {drawer}
        </>
      )
    }
    return (
      <>
        <IdleView onSubmit={submitNew} onOpenHistory={openHistory} />
        {drawer}
      </>
    )
  }

  if (error) {
    return (
      <>
        <div className="grid gap-3 py-8 text-center">
          <p className="text-sm text-danger">{error}</p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button type="button" onClick={goNew} className={GHOST_BTN}>
              <Plus size={16} /> 新建
            </button>
            <button type="button" onClick={openHistory} className={GHOST_BTN}>
              <History size={16} /> 历史
            </button>
          </div>
        </div>
        {drawer}
      </>
    )
  }

  if (!job) {
    return (
      <>
        <p className="py-12 text-center text-sm text-muted">加载中</p>
        {drawer}
      </>
    )
  }

  if (job.status === 'COMPLETED') {
    return (
      <>
        <DoneView
          job={job}
          onNew={goNew}
          onOpenHistory={openHistory}
          onDownloadAudio={downloadAudio}
          onCopy={copySummary}
          onDownloadMarkdown={downloadMarkdown}
        />
        {drawer}
      </>
    )
  }

  return (
    <>
      <RunningView
        job={job}
        onCancel={cancel}
        onRetry={retry}
        onNew={goNew}
        onOpenHistory={openHistory}
        busy={actionBusy}
      />
      {drawer}
    </>
  )
}
