import {useCallback, useEffect, useRef, useState} from 'react'
import {ChevronDown, History, Plus} from 'lucide-react'
import {useLocation} from 'wouter'
import {
  cancelJob,
  createJob,
  downloadJobAudio,
  getConfigDefaults,
  getJob,
  resummarizeJob,
  resendEmail,
  retryJob,
} from '../lib/api'
import type {ConfigDefaults, Job, JobOptionOverrides} from '../lib/api'
import {isRunning} from '../lib/jobStatus'
import {triggerDownload} from '../lib/download'
import {transcriptToSrt} from '../lib/subtitle'
import {clearActive, readActive, subscribeActive, writeActive} from '../lib/activeJob'
import {useJob} from '../hooks/useJob'
import {useJobStream} from '../hooks/useJobStream'
import {useRuntimeConfig} from '../hooks/useRuntimeConfig'
import {useStickToBottom} from '../hooks/useStickToBottom'
import {useTerminalToast} from '../hooks/useTerminalToast'
import {useToast} from '../components/ToastProvider'
import {ConfirmDialog} from '../components/ConfirmDialog'
import {IconButton} from '../components/IconButton'
import {PageLoading} from '../components/Spinner'
import {IdleView} from './workspace/IdleView'
import {RunningView} from './workspace/RunningView'
import {DoneView} from './workspace/DoneView'

interface WorkspaceProps {
  jobId: string | null
}

/**
 * Workspace shell：仅负责状态编排（jobId、defaults、actions、SSE 订阅）和路由分支
 * （Idle / Running / Done / Recovery / Error）。具体视图与副作用全在子组件 / hook 里。
 */
export function Workspace({jobId}: WorkspaceProps) {
  const [, navigate] = useLocation()
  const toast = useToast()
  const {job, setJob, error, refresh} = useJob(jobId)
  const [actionBusy, setActionBusy] = useState(false)
  const [cancelPending, setCancelPending] = useState(false)
  const [emailBusy, setEmailBusy] = useState(false)
  const [duplicateJob, setDuplicateJob] = useState<{url: string; jobId: string} | null>(null)
  const [duplicateBusy, setDuplicateBusy] = useState(false)
  const [resummaryConfirmOpen, setResummaryConfirmOpen] = useState(false)

  // 拉一次后端默认值；retry/resume 时把 llm_model + llm_base_url 作为 overrides
  // 传过去，避免历史 job 里残留的旧供应商快照（比如老 Kimi job）继续使用过期配置。
  const [defaults, setDefaults] = useState<ConfigDefaults | null>(null)
  useEffect(() => {
    let cancelled = false
    void getConfigDefaults()
      .then((res) => {
        if (!cancelled) setDefaults(res.defaults)
      })
      .catch(() => {
        // 拉失败不致命：退化为不传 overrides（即沿用 job 自身快照）。
      })
    return () => {
      cancelled = true
    }
  }, [])
  const currentLlmOverrides = useCallback((): JobOptionOverrides => {
    if (!defaults) return {}
    return {llm_model: defaults.llm_model, llm_base_url: defaults.llm_base_url}
  }, [defaults])

  // 流式总结期间的跳底浮标：用户不主动向上看就自动跟随新内容。
  const streaming = job?.status === 'SUMMARIZING'
  const summaryLen = job?.summary?.length ?? 0
  const {showJump, jumpToBottom} = useStickToBottom(streaming, [summaryLen])

  // 收到 SSE CANCELED / FAILED 时把「取消中…」清掉。
  // 单独把 status 拎出来作为依赖：jobStatus 字符串比较一致才会触发。
  const jobStatus = job?.status
  useEffect(() => {
    if (!jobStatus) return
    if (!isRunning(jobStatus)) {
      setCancelPending(false)
    }
  }, [jobStatus])

  // SSE patch：流式更新 status / summary / progress / 等等。
  const patchJob = useCallback(
    (partial: Partial<Job>) => {
      setJob((current) => {
        if (!current) return current
        const next = {...current, ...partial}
        // TRANSCRIPT_READY SSE 只带前几行 preview；如果详情 snapshot 已有完整字幕，
        // 不能让晚到的 preview 把完整 transcript 覆盖掉。
        if (partial.transcript && (current.transcript?.length ?? 0) > partial.transcript.length) {
          next.transcript = current.transcript
        }
        return next
      })
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

  useTerminalToast(job, jobId)

  // SSE 的 COMPLETED status 不带完整 transcript。实时跑完时，当前 state 可能仍只有
  // TRANSCRIPT_READY 的 preview；终态到达后拉一次详情 snapshot，补齐字幕全文等大字段。
  const previousJobStatusRef = useRef(jobStatus)
  useEffect(() => {
    const previous = previousJobStatusRef.current
    previousJobStatusRef.current = jobStatus
    if (jobStatus === 'COMPLETED' && previous && previous !== 'COMPLETED') {
      void refresh()
    }
  }, [jobStatus, refresh])

  // ---- 状态恢复 / 跨标签同步 ----

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
        if (isRunning(response.job.status)) {
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

  useEffect(() => {
    return subscribeActive((pointer) => {
      if (pointer && jobId == null) {
        navigate(`/jobs/${pointer.jobId}`)
      }
    })
  }, [jobId, navigate])

  // ---- actions ----

  // 默认行为：邮件能用就发，不能用就别传 email_enabled=true，
  // 否则后端会因为 EMAIL_DEFAULT_RECIPIENT 没配直接 400 拒。
  const runtime = useRuntimeConfig()
  const newSummaryOptions = useCallback((): Partial<JobOptionOverrides> => {
    const options: Partial<JobOptionOverrides> = {task_type: 'summary'}
    if (runtime?.email_configured) options.email_enabled = true
    return options
  }, [runtime?.email_configured])

  const submitNew = async (url: string) => {
    const response = await createJob(url, newSummaryOptions())
    if (response.deduped) {
      setDuplicateJob({url, jobId: response.job_id})
      return
    }
    writeActive({jobId: response.job_id, url})
    toast.success('已开始总结')
    navigate(`/jobs/${response.job_id}`)
  }

  const viewDuplicateSummary = () => {
    if (!duplicateJob) return
    const {jobId} = duplicateJob
    setDuplicateJob(null)
    navigate(`/jobs/${jobId}`)
  }

  const resummarizeDuplicate = async () => {
    if (!duplicateJob) return
    setDuplicateBusy(true)
    const {url, jobId: sourceJobId} = duplicateJob
    try {
      const response = await resummarizeJob(sourceJobId, newSummaryOptions())
      writeActive({jobId: response.job_id, url})
      setDuplicateJob(null)
      toast.success('已开始重新总结')
      navigate(`/jobs/${response.job_id}`)
    } catch (err) {
      toast.error('重新总结失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setDuplicateBusy(false)
    }
  }

  const resummarizeCurrent = async () => {
    if (!job) return
    setActionBusy(true)
    const taskName = job.title || undefined
    try {
      const response = await resummarizeJob(job.id, newSummaryOptions())
      writeActive({jobId: response.job_id, url: job.url})
      setResummaryConfirmOpen(false)
      toast.success('已开始重新总结', undefined, {taskName})
      navigate(`/jobs/${response.job_id}`)
    } catch (err) {
      toast.error('重新总结失败', err instanceof Error ? err.message : '请重试', {taskName})
    } finally {
      setActionBusy(false)
    }
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
    const taskName = job?.title || undefined
    try {
      await cancelJob(jobId)
      await refresh()
      toast.info('已请求取消', undefined, {taskName})
    } catch (err) {
      window.clearTimeout(safetyTimeout)
      setCancelPending(false)
      toast.error('取消失败', err instanceof Error ? err.message : '请重试', {taskName})
    } finally {
      setActionBusy(false)
    }
  }

  const resendCurrentEmail = async () => {
    if (!jobId) return
    setEmailBusy(true)
    const taskName = job?.title || undefined
    try {
      await resendEmail(jobId)
      await refresh()
      toast.success('已重发邮件', undefined, {taskName})
    } catch (err) {
      toast.error('重发失败', err instanceof Error ? err.message : '请重试', {taskName})
    } finally {
      setEmailBusy(false)
    }
  }

  const retry = async () => {
    if (!jobId) return
    setActionBusy(true)
    const taskName = job?.title || undefined
    try {
      await retryJob(jobId, currentLlmOverrides())
      // 必须先 kick SSE 再 refresh：从 FAILED 走出来后旧 SSE 已死，不重连就拿不到
      // 后续 progress / status 事件，页面会卡在某个中间状态。
      setStreamReconnectKey((k) => k + 1)
      await refresh()
      toast.info('已重试', undefined, {taskName})
    } catch (err) {
      toast.error('重试失败', err instanceof Error ? err.message : '请重试', {taskName})
    } finally {
      setActionBusy(false)
    }
  }

  const downloadAudio = async () => {
    if (!jobId) return
    const taskName = job?.title || undefined
    try {
      const {blob, filename} = await downloadJobAudio(jobId)
      triggerDownload(blob, filename || `${job?.title || jobId}.wav`)
      toast.success('音频已下载', undefined, {taskName})
    } catch (err) {
      toast.error('下载音频失败', err instanceof Error ? err.message : '请重试', {taskName})
    }
  }

  const copySummary = async () => {
    if (!job?.summary) return
    const taskName = job.title || undefined
    try {
      await navigator.clipboard.writeText(job.summary)
      toast.success('已复制', undefined, {taskName})
    } catch {
      toast.error('复制失败', '请手动选中复制', {taskName})
    }
  }

  const downloadMarkdown = () => {
    if (!job?.summary) return
    const blob = new Blob([job.summary], {type: 'text/markdown;charset=utf-8'})
    triggerDownload(blob, `${job.title || 'summary'}.md`)
    toast.success('Markdown 已下载', undefined, {taskName: job.title || undefined})
  }

  const downloadSubtitle = () => {
    const taskName = job?.title || undefined
    const srt = job?.transcript?.length ? transcriptToSrt(job.transcript) : ''
    if (!srt) {
      toast.error('没有可下载的字幕', undefined, {taskName})
      return
    }
    const blob = new Blob([srt], {type: 'application/x-subrip;charset=utf-8'})
    triggerDownload(blob, `${job?.title || 'subtitle'}.srt`)
    toast.success('字幕已下载', undefined, {taskName})
  }

  const goNew = () => {
    clearActive()
    navigate('/')
  }
  const openHistory = () => navigate('/history')
  const openStats = () => navigate('/stats')

  // ---- render ----

  if (!jobId) {
    if (recovering) {
      return <PageLoading label="恢复上次任务…" />
    }
    return (
      <>
        <IdleView onSubmit={submitNew} onOpenHistory={openHistory} />
        <ConfirmDialog
          open={duplicateJob != null}
          title="这条视频之前总结过"
          description="可以直接查看原总结；重新总结会复用已有字幕创建一条新总结任务，原记录会保留在历史中。"
          cancelLabel="取消"
          secondaryLabel="查看原总结"
          confirmLabel="重新总结"
          loading={duplicateBusy}
          onSecondary={viewDuplicateSummary}
          onConfirm={() => void resummarizeDuplicate()}
          onCancel={() => setDuplicateJob(null)}
        />
      </>
    )
  }

  if (error) {
    return (
      <div className="grid gap-3 py-8 text-center">
        <p className="text-sm text-danger">{error}</p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <IconButton icon={<Plus size={18} />} label="新建" onClick={goNew} />
          <IconButton icon={<History size={18} />} label="历史" onClick={openHistory} />
        </div>
      </div>
    )
  }

  if (!job) {
    return <PageLoading label="加载任务…" />
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
          onOpenStats={openStats}
          onDownloadAudio={downloadAudio}
          onCopy={copySummary}
          onDownloadMarkdown={downloadMarkdown}
          onDownloadSubtitle={downloadSubtitle}
          onResendEmail={resendCurrentEmail}
          onResummarize={() => setResummaryConfirmOpen(true)}
          emailBusy={emailBusy}
          resummarizeBusy={actionBusy}
        />
        <ConfirmDialog
          open={resummaryConfirmOpen}
          title="重新总结这个视频？"
          description="会复用当前字幕创建一条新的总结任务，原总结会继续保留在历史记录中。"
          confirmLabel="重新总结"
          loading={actionBusy}
          onConfirm={() => void resummarizeCurrent()}
          onCancel={() => setResummaryConfirmOpen(false)}
        />
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
        onOpenStats={openStats}
        busy={actionBusy}
        cancelPending={cancelPending}
      />
      {jumpFloater}
    </>
  )
}
