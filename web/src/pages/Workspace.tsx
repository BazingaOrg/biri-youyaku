import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {ChevronDown, Copy, ExternalLink, FileDown, History, Mail, Music, Plus, RotateCw, Sparkles, XCircle} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import {useLocation} from 'wouter'
import {cancelJob, createJob, downloadJobAudio, getJob, resendEmail, resumeJob, retryJob} from '../lib/api'
import type {Job, JobOptionOverrides, JobStatus} from '../lib/api'
import {isValidBiliUrl, sanitizeBiliInput} from '../lib/url'
import {formatDuration} from '../lib/format'
import {friendlyError} from '../lib/errorMap'
import {useJob} from '../hooks/useJob'
import {useJobStream} from '../hooks/useJobStream'
import {useRuntimeConfig} from '../hooks/useRuntimeConfig'
import {useToast} from '../components/ToastProvider'
import {UrlInput} from '../components/UrlInput'
import {StepCarousel, type StepDef, type StepState} from '../components/StepCarousel'
import {HistoryDrawer} from '../components/HistoryDrawer'
import {IconButton} from '../components/IconButton'
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
    // 提交时再 sanitize 一次：handle 直接键入 / 历史回填等不走 paste 的入口。
    const cleaned = sanitizeBiliInput(url)
    if (!isValidBiliUrl(cleaned)) {
      setError('请输入有效的 B 站视频链接')
      return
    }
    if (cleaned !== url) {
      setUrl(cleaned)
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit(cleaned)
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
          粘贴 B 站链接，自动总结
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
        <div className="flex flex-wrap items-center justify-center gap-3">
          <IconButton
            icon={busy ? <RotateCw size={20} className="animate-spin" /> : <Sparkles size={22} />}
            label={busy ? '处理中…' : '开始总结'}
            onClick={() => void submit()}
            disabled={busy || url.trim().length === 0}
            variant="primary"
            size="lg"
          />
          <IconButton icon={<History size={20} />} label="历史" onClick={onOpenHistory} size="lg" />
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
    return (
      <p>
        正在生成总结… 模型 <span className="break-all text-ink">{job.options.llm_model}</span>
      </p>
    )
  }
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
  cancelPending,
}: {
  job: Job
  onCancel: () => void
  onRetry: () => void
  onNew: () => void
  onOpenHistory: () => void
  busy: boolean
  cancelPending: boolean
}) {
  const steps = useMemo(() => buildSteps(job), [job])
  const currentIdx = statusToStepIndex(job.status)
  const failure = job.error_message ? friendlyError(job.error_code, job.error_message, job.error_stage) : null
  const canCancel = RUNNING_STATUSES.includes(job.status)
  const canRetry = job.status === 'FAILED'
  const toast = useToast()

  const copyErrorDetail = async () => {
    if (!failure) return
    const detail = [
      `Job ID: ${job.id}`,
      `Stage: ${job.error_stage || '-'}`,
      `Error code: ${job.error_code || '-'}`,
      `Message: ${job.error_message || '-'}`,
    ].join('\n')
    try {
      await navigator.clipboard.writeText(detail)
      toast.success('错误详情已复制')
    } catch {
      toast.error('复制失败', '请手动选中复制')
    }
  }

  return (
    <div className="grid gap-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <IconButton icon={<Plus size={18} />} label="新建" onClick={onNew} />
        <IconButton icon={<History size={18} />} label="历史" onClick={onOpenHistory} />
      </div>
      <MetaBar job={job} />
      <StepCarousel steps={steps} currentIndex={currentIdx} />
      {failure && (
        <div className="rounded-2xl border border-danger/50 bg-danger/20 p-4 text-sm text-danger shadow-card">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-base font-semibold">{failure.title}</p>
            <button
              type="button"
              onClick={copyErrorDetail}
              className="inline-flex items-center gap-1 rounded-lg border border-danger/40 bg-panel/40 px-2 py-1 text-xs text-danger transition hover:bg-danger/30"
            >
              <Copy size={12} /> 复制
            </button>
          </div>
          <p className="mt-1.5 break-words leading-6 text-danger/90">{failure.message}</p>
        </div>
      )}
      {(canCancel || canRetry) && (
        <div className="flex flex-wrap items-center justify-center gap-2">
          {canCancel && (
            <IconButton
              icon={cancelPending ? <RotateCw size={18} className="animate-spin" /> : <XCircle size={18} />}
              label={cancelPending ? '取消中…' : '取消'}
              onClick={onCancel}
              disabled={cancelPending}
              variant="danger"
            />
          )}
          {canRetry && (
            <IconButton
              icon={<RotateCw size={18} />}
              label={failure?.actionLabel || '重试'}
              onClick={onRetry}
              disabled={busy}
              variant="primary"
            />
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
  onResendEmail,
  emailBusy,
}: {
  job: Job
  onNew: () => void
  onOpenHistory: () => void
  onDownloadAudio: () => void
  onCopy: () => void
  onDownloadMarkdown: () => void
  onResendEmail: () => void
  emailBusy: boolean
}) {
  return (
    <div className="grid gap-4 py-4">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <IconButton icon={<Plus size={18} />} label="新建" onClick={onNew} />
        <IconButton
          icon={<Music size={18} />}
          label="下载音频"
          onClick={onDownloadAudio}
          disabled={!job.audio_available}
        />
        <IconButton
          icon={<Copy size={18} />}
          label="复制总结"
          onClick={onCopy}
          disabled={!job.summary}
        />
        <IconButton
          icon={<FileDown size={18} />}
          label="下载 Markdown"
          onClick={onDownloadMarkdown}
          disabled={!job.summary}
        />
        <IconButton icon={<History size={18} />} label="历史" onClick={onOpenHistory} />
      </div>
      <MetaBar job={job} />
      {job.email_error && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          <p className="break-words leading-6">
            总结已完成，邮件未送达：{job.email_error}
          </p>
          <button
            type="button"
            onClick={onResendEmail}
            disabled={emailBusy}
            className="inline-flex items-center gap-1 rounded-lg border border-warning/30 px-2 py-1 text-xs text-warning transition hover:bg-warning/20 disabled:opacity-60"
          >
            {emailBusy ? <RotateCw size={12} className="animate-spin" /> : <Mail size={12} />}
            重发邮件
          </button>
        </div>
      )}
      <section className="rounded-3xl bg-panel p-4 shadow-card sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-[-0.012em]">视频总结</h2>
          <span className="truncate text-xs text-muted">{job.options.llm_model}</span>
        </div>
        {job.summary ? (
          <div className="prose prose-sm max-w-none break-words text-ink dark:prose-invert prose-headings:tracking-[-0.012em] prose-a:text-brand [&_pre]:overflow-x-auto [&_table]:block [&_table]:overflow-x-auto [&_code]:break-all">
            <ReactMarkdown>{job.summary}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-muted">没有总结内容</p>
        )}
      </section>
    </div>
  )
}

// 跳到底浮标：流式总结时若用户已滚到接近底部，自动跟随；用户向上看时不打扰。
//
// `awayFromBottomRef` 默认 true（视为「不在底部」），mount 后第一次 scroll 事件
// 或第一次内容增长会同步真实位置。这避免了用户进入 SUMMARIZING 时即使在页面中段
// 阅读也被强制顶到底的体验问题。
function useStickToBottom(active: boolean, deps: unknown[]) {
  const awayFromBottomRef = useRef(true)
  const [showJump, setShowJump] = useState(false)

  // 工具：基于当前 viewport 判断是否「足够靠近底部」（容差 64px）
  const computeNearBottom = () => {
    if (typeof window === 'undefined') return true
    const doc = document.documentElement
    return window.innerHeight + window.scrollY >= doc.scrollHeight - 64
  }

  useEffect(() => {
    if (!active) {
      awayFromBottomRef.current = true
      setShowJump(false)
      return
    }
    // 进入 active 时立刻同步一次真实位置；用户已经在底部才会开启「自动跟随」
    awayFromBottomRef.current = !computeNearBottom()
    setShowJump(awayFromBottomRef.current)
    const onScroll = () => {
      const away = !computeNearBottom()
      awayFromBottomRef.current = away
      setShowJump(away)
    }
    window.addEventListener('scroll', onScroll, {passive: true})
    return () => window.removeEventListener('scroll', onScroll)
  }, [active])

  useEffect(() => {
    if (!active || awayFromBottomRef.current) return
    // 用户处于底部时才自动跟随新内容
    window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'auto'})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ...deps])

  const jumpToBottom = () => {
    if (typeof window === 'undefined') return
    window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'smooth'})
  }
  return {showJump, jumpToBottom}
}

// ---------- Workspace shell ----------

export function Workspace({jobId}: WorkspaceProps) {
  const [, navigate] = useLocation()
  const toast = useToast()
  const {job, setJob, error, refresh} = useJob(jobId)
  const [actionBusy, setActionBusy] = useState(false)
  const [cancelPending, setCancelPending] = useState(false)
  const [emailBusy, setEmailBusy] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const autoResumedRef = useRef<string | null>(null)
  const notifiedRef = useRef<string | null>(null)

  // 流式总结期间的跳底浮标：用户不主动向上看就自动跟随新内容。
  const streaming = job?.status === 'SUMMARIZING'
  const summaryLen = job?.summary?.length ?? 0
  const {showJump, jumpToBottom} = useStickToBottom(streaming, [summaryLen])

  // 收到 SSE CANCELED / FAILED 时把「取消中…」清掉。
  // 单独把 status 拎出来作为依赖：jobStatus 字符串比较一致才会触发。
  const jobStatus = job?.status
  useEffect(() => {
    if (!jobStatus) return
    if (!RUNNING_STATUSES.includes(jobStatus)) {
      setCancelPending(false)
    }
  }, [jobStatus])

  const patchJob = useCallback(
    (partial: Partial<Job>) => {
      setJob((current) => (current ? {...current, ...partial} : current))
    },
    [setJob],
  )
  // SSE 断流（Cloudflare Tunnel 90s 空闲、iOS Safari 后台等）重连后，立刻拉
  // 一次全量 snapshot 修正漂移（避免漏掉断流期间的 status / summary 等更新）。
  const reconnectedRefresh = useCallback(() => {
    void refresh()
  }, [refresh])
  // streamReconnectKey：retry 后 bump 一下强制 SSE 重新订阅。FAILED 期间后端
  // stream 路由立刻 return，前端 terminalRef 会锁死自动重连——retry 必须显式 kick。
  const [streamReconnectKey, setStreamReconnectKey] = useState(0)
  useJobStream(jobId, patchJob, {
    onReconnected: reconnectedRefresh,
    reconnectKey: streamReconnectKey,
  })

  // 切换任务时重置一次性 flag
  useEffect(() => {
    autoResumedRef.current = null
    notifiedRef.current = null
  }, [jobId])

  // TRANSCRIPT_READY 自动 resume —— 不再二次确认
  //
  // 注意：只在 status === TRANSCRIPT_READY 这一刻锁；一旦离开（不论是进 SUMMARIZING
  // 还是 retry 回到 PENDING）就清锁。否则同一 jobId 的 retry 会因为「之前 resume 过」
  // 而被跳过，整条 pipeline 卡在 TRANSCRIPT_READY 永远不再向前走。
  useEffect(() => {
    if (!job || !jobId) return
    if (job.status !== 'TRANSCRIPT_READY') {
      if (autoResumedRef.current === jobId) {
        autoResumedRef.current = null
      }
      return
    }
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
  //
  // notifiedRef 必须在「离开终态」时清掉，否则 retry 让任务从 FAILED 重跑，再次进入
  // FAILED 时会因为 key 还是 `<id>:FAILED` 而被静默跳过 toast。同 autoResumedRef 套路。
  useEffect(() => {
    if (!job || !jobId) return
    const isTerminal =
      job.status === 'COMPLETED' || job.status === 'FAILED' || job.status === 'CANCELED'
    if (!isTerminal) {
      notifiedRef.current = null
      return
    }
    const key = `${jobId}:${job.status}`
    if (notifiedRef.current === key) return
    if (job.status === 'COMPLETED') {
      notifiedRef.current = key
      clearActive(jobId)
      const detail = !job.options.email_enabled
        ? '已生成'
        : job.email_error
          ? '总结已生成，邮件未送达'
          : '已发送到邮箱'
      toast.success('总结完成', detail)
    }
    if (job.status === 'FAILED' && job.error_message) {
      notifiedRef.current = key
      clearActive(jobId)
      const fe = friendlyError(job.error_code, job.error_message, job.error_stage)
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

  // 默认行为：邮件能用就发，不能用就别传 email_enabled=true，
  // 否则后端会因为 EMAIL_DEFAULT_RECIPIENT 没配直接 400 拒。
  const runtime = useRuntimeConfig()
  const submitNew = async (url: string) => {
    const options: Partial<JobOptionOverrides> = {task_type: 'summary'}
    if (runtime?.email_configured) options.email_enabled = true
    const response = await createJob(url, options)
    writeActive({jobId: response.job_id, url})
    toast.success('已开始')
    navigate(`/jobs/${response.job_id}`)
  }

  const cancel = async () => {
    if (!jobId) return
    setActionBusy(true)
    // cancelPending 立即生效，按钮即刻变「取消中…」；后端真正切到 CANCELED 时
    // 由上面那个 useEffect 把它清掉，避免「点了没反应」的错觉。
    setCancelPending(true)
    // 安全超时：如果 SSE 通路异常导致 CANCELED 状态没送达，15s 后强制解除 pending
    // 避免按钮永远转。已收到终态时上面的 useEffect 会先清掉，timeout 是 no-op。
    const safetyTimeout = window.setTimeout(() => setCancelPending(false), 15000)
    try {
      await cancelJob(jobId)
      await refresh()
      toast.info('已请求取消')
    } catch (err) {
      window.clearTimeout(safetyTimeout)
      setCancelPending(false)
      toast.error('取消失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setActionBusy(false)
    }
  }

  const resendCurrentEmail = async () => {
    if (!jobId) return
    setEmailBusy(true)
    try {
      await resendEmail(jobId)
      await refresh()
      toast.success('已重发邮件')
    } catch (err) {
      toast.error('重发失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setEmailBusy(false)
    }
  }

  const retry = async () => {
    if (!jobId) return
    setActionBusy(true)
    try {
      await retryJob(jobId)
      // 必须先 kick SSE 再 refresh：从 FAILED 走出来后旧 SSE 已死，不重连就拿不到
      // 后续 progress / status 事件，页面会卡在某个中间状态。
      setStreamReconnectKey((k) => k + 1)
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
      refreshKey={
        // 只在「进入终态」时刷新历史列表，避免运行中每个 status 变化都拉一次
        jobId ??
        (job?.status === 'COMPLETED' || job?.status === 'FAILED' || job?.status === 'CANCELED'
          ? job.status
          : null)
      }
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
            <IconButton icon={<Plus size={18} />} label="新建" onClick={goNew} />
            <IconButton icon={<History size={18} />} label="历史" onClick={openHistory} />
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

  // 流式总结时的跳到底浮标
  const jumpFloater = showJump ? (
    <button
      type="button"
      onClick={jumpToBottom}
      aria-label="跳到底部"
      className="fixed bottom-5 right-5 z-30 grid h-11 w-11 place-items-center rounded-full border border-line bg-panel text-muted shadow-card transition hover:text-brand"
    >
      <ChevronDown size={20} />
    </button>
  ) : null

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
          onResendEmail={resendCurrentEmail}
          emailBusy={emailBusy}
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
        cancelPending={cancelPending}
      />
      {jumpFloater}
      {drawer}
    </>
  )
}
