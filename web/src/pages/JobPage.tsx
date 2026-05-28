import {useCallback, useEffect, useState} from 'react'
import {Download, ExternalLink, Mail, MoreHorizontal, Play, RotateCw, XCircle} from 'lucide-react'
import {cancelJob, downloadJobAudio, replaceTranscript, resendEmail, resumeJob, retryJob} from '../lib/api'
import type {Job} from '../lib/api'
import {formatDuration} from '../lib/format'
import {useJob} from '../hooks/useJob'
import {useJobStream} from '../hooks/useJobStream'
import {JobProgress} from '../components/JobProgress'
import {SummaryView} from '../components/SummaryView'
import {TranscriptView} from '../components/TranscriptView'
import {OptionsForm} from '../components/OptionsForm'
import type {ConfigDefaults, JobOptionOverrides} from '../lib/api'
import {getConfigDefaults} from '../lib/api'
import {useToast} from '../components/ToastProvider'
import {friendlyError} from '../lib/errorMap'
import {useShortcuts} from '../hooks/useShortcuts'

interface JobPageProps {
  jobId: string
}

export function JobPage({jobId}: JobPageProps) {
  const {job, setJob, error, refresh} = useJob(jobId)
  const [defaults, setDefaults] = useState<ConfigDefaults | null>(null)
  const [options, setOptions] = useState<JobOptionOverrides>({})
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [defaultsLoading, setDefaultsLoading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [notifiedCompleted, setNotifiedCompleted] = useState(false)
  const [notifiedError, setNotifiedError] = useState<string | null>(null)
  const [moreOpen, setMoreOpen] = useState(false)
  const [audioPreviewUrl, setAudioPreviewUrl] = useState<string | null>(null)
  const toast = useToast()
  const patch = useCallback((partial: Partial<Job>) => {
    setJob((current) => current ? {...current, ...partial} : current)
  }, [setJob])
  useJobStream(jobId, patch)

  useEffect(() => {
    setDefaults(null)
    setOptions({})
    setOptionsOpen(false)
    setActionError(null)
    setStarting(false)
    setNotifiedCompleted(false)
    setNotifiedError(null)
    setMoreOpen(false)
    setAudioPreviewUrl(null)
  }, [jobId])

  useEffect(() => {
    let disposed = false
    let objectUrl: string | null = null
    if (!job?.audio_available) {
      setAudioPreviewUrl(null)
      return undefined
    }
    downloadJobAudio(jobId)
      .then(({blob}) => {
        if (disposed) {
          return
        }
        objectUrl = URL.createObjectURL(blob)
        setAudioPreviewUrl(objectUrl)
      })
      .catch(() => setAudioPreviewUrl(null))
    return () => {
      disposed = true
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [job?.audio_available, jobId])

  useEffect(() => {
    if (job?.status === 'TRANSCRIPT_READY' && (job.transcript?.length ?? 0) === 0) {
      void refresh()
    }
  }, [job?.status, job?.transcript?.length, refresh])

  useEffect(() => {
    if (job?.status !== 'TRANSCRIPT_READY' || defaults || defaultsLoading) {
      return
    }
    setDefaultsLoading(true)
    getConfigDefaults()
      .then((response) => {
        setDefaults(response.defaults)
        setActionError(null)
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : '加载默认配置失败'
        setActionError(message)
        toast.error('加载默认配置失败', message)
      })
      .finally(() => setDefaultsLoading(false))
  }, [defaults, defaultsLoading, job?.status, toast])

  useEffect(() => {
    if (job?.status === 'COMPLETED' && !notifiedCompleted) {
      toast.success('总结已完成', job.options.email_enabled ? '总结已生成，邮件发送流程已完成。' : '总结已生成。')
      setNotifiedCompleted(true)
    }
    if (job?.status === 'FAILED' && job.error_message && notifiedError !== job.error_message) {
      const nextError = friendlyError(job.error_code, job.error_message)
      toast.error(nextError.title, nextError.message)
      setNotifiedError(job.error_message)
    }
  }, [job?.error_code, job?.error_message, job?.options.email_enabled, job?.status, notifiedCompleted, notifiedError, toast])

  const resend = async () => {
    setActionError(null)
    try {
      await resendEmail(jobId)
      toast.success('邮件已发送', job?.title || '总结邮件已重新发送。')
    } catch (err) {
      const message = err instanceof Error ? err.message : '邮件发送失败'
      setActionError(message)
      toast.error('邮件发送失败', message)
    }
  }

  const cancel = async () => {
    setActionError(null)
    try {
      await cancelJob(jobId)
      await refresh()
      toast.info('任务已取消', job?.title || jobId)
    } catch (err) {
      const message = err instanceof Error ? err.message : '取消任务失败'
      setActionError(message)
      toast.error('取消任务失败', message)
    }
  }

  const downloadAudio = async () => {
    setActionError(null)
    try {
      const {blob, filename} = await downloadJobAudio(jobId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename || `${job?.title || jobId}.wav`
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success('音频已开始下载')
    } catch (err) {
      const message = err instanceof Error ? err.message : '下载音频失败'
      setActionError(message)
      toast.error('下载音频失败', message)
    }
  }

  const startSummary = async () => {
    setActionError(null)
    setStarting(true)
    try {
      await resumeJob(jobId, options)
      await refresh()
    } catch (err) {
      const message = err instanceof Error ? err.message : '启动总结失败'
      setActionError(message)
      toast.error('启动总结失败', message)
    } finally {
      setStarting(false)
    }
  }

  const canCancel = job ? ['PENDING', 'FETCHING_META', 'DOWNLOADING_AUDIO', 'TRANSCRIBING', 'SUMMARIZING', 'EMAILING'].includes(job.status) : false
  const canStartSummary = job?.status === 'TRANSCRIPT_READY'
  const canResendEmail = job?.status === 'COMPLETED' && Boolean(job.summary)
  const canRetry = job?.status === 'FAILED'
  const failure = job?.error_message ? friendlyError(job.error_code, job.error_message) : null

  const retry = async () => {
    setActionError(null)
    setStarting(true)
    try {
      await retryJob(jobId, options)
      await refresh()
      toast.info('任务已重试', job?.title || jobId)
    } catch (err) {
      const message = err instanceof Error ? err.message : '重试任务失败'
      setActionError(message)
      toast.error('重试任务失败', message)
    } finally {
      setStarting(false)
    }
  }

  const uploadTranscript = async (items: Job['transcript']) => {
    setActionError(null)
    try {
      await replaceTranscript(jobId, items)
      await refresh()
      toast.success('字幕已覆盖', '确认后可重新生成总结。')
    } catch (err) {
      const message = err instanceof Error ? err.message : '覆盖字幕失败'
      setActionError(message)
      toast.error('覆盖字幕失败', message)
    }
  }

  useShortcuts({
    onSubmit: () => {
      if (canStartSummary) {
        void startSummary()
      } else if (canRetry) {
        void retry()
      }
    },
    onCancel: canCancel ? cancel : undefined,
  })

  if (error) {
    return <p className="rounded-lg bg-red-50 p-4 text-danger">{error}</p>
  }

  if (!job) {
    return <div className="rounded-lg bg-panel p-6 text-muted shadow-card">加载中</div>
  }

  return (
    <div className="grid gap-5 pb-24 md:pb-0">
      <section className="rounded-3xl bg-panel p-4 shadow-card sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted">
              <span className="rounded-full bg-brandSoft px-2.5 py-1 text-brand">{job.bvid || '等待元信息'}</span>
              <span className="rounded-full bg-lift px-2.5 py-1">{job.subtitle_source === 'platform' ? '官方字幕' : job.subtitle_source === 'asr' ? 'ASR' : '字幕未定'}</span>
              <a href={job.url} target="_blank" rel="noreferrer" className="inline-flex min-h-8 items-center gap-1 rounded-xl px-2 text-muted transition hover:bg-lift hover:text-ink">
                视频源
                <ExternalLink size={13} />
              </a>
            </div>
            <h1 className="mt-3 text-2xl font-semibold leading-snug">{job.title || job.url}</h1>
            <p className="mt-2 text-sm text-muted">
              {job.author || '未知 UP'} · {formatDuration(job.duration)} · {new Date(job.created_at).toLocaleString('zh-CN')}
            </p>
          </div>
          <div className="hidden flex-wrap justify-end gap-2 md:flex">
            {canStartSummary && (
              <button type="button" onClick={startSummary} disabled={starting} className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-brand px-5 text-sm font-semibold text-white transition hover:brightness-105 active:scale-95 disabled:opacity-50">
                <Play size={17} />
                确认并总结
              </button>
            )}
            {canCancel && (
              <button type="button" onClick={cancel} className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition hover:bg-line/70 active:scale-95">
                <XCircle size={16} />
                取消
              </button>
            )}
            {canResendEmail && (
              <button type="button" onClick={resend} className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-lift px-4 text-sm font-medium text-muted transition hover:bg-line/70 active:scale-95">
                <Mail size={16} />
                重发邮件
              </button>
            )}
            {canRetry && (
              <button type="button" onClick={retry} disabled={starting} className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-brand px-5 text-sm font-semibold text-white transition hover:brightness-105 active:scale-95 disabled:opacity-50">
                <RotateCw size={16} />
                重试
              </button>
            )}
            <div className="relative">
              <button type="button" aria-label="更多操作" onClick={() => setMoreOpen((value) => !value)} className="grid h-11 w-11 place-items-center rounded-2xl bg-lift text-muted transition hover:bg-line/70 active:scale-95">
                <MoreHorizontal size={18} />
              </button>
              {moreOpen && (
                <div className="absolute right-0 top-12 z-10 grid min-w-36 gap-1 rounded-2xl bg-panel p-2 shadow-card">
                  <button type="button" onClick={() => { setMoreOpen(false); void refresh() }} className="inline-flex min-h-9 items-center gap-2 rounded-xl px-3 text-sm text-muted transition hover:bg-lift">
                    <RotateCw size={15} />
                    刷新
                  </button>
                  <button type="button" onClick={() => { setMoreOpen(false); void downloadAudio() }} disabled={!job.audio_available} className="inline-flex min-h-9 items-center gap-2 rounded-xl px-3 text-sm text-muted transition hover:bg-lift disabled:opacity-40">
                    <Download size={15} />
                    下载音频
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
        {failure && (
          <div className="mt-3 rounded-2xl bg-red-50 p-3 text-sm text-danger">
            <p className="font-semibold">{failure.title}</p>
            <p className="mt-1 leading-6">{failure.message}</p>
          </div>
        )}
        {actionError && (
          <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-danger">{actionError}</p>
        )}
      </section>
      <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="grid content-start gap-5 lg:sticky lg:top-24">
          <JobProgress status={job.status} emailEnabled={job.options.email_enabled} subtitleSource={job.subtitle_source} downloadPercent={job.download_progress?.percent} />
          {canStartSummary && (
            <section className="rounded-3xl bg-panel p-4 shadow-card">
              <div className="rounded-2xl bg-amber-50 p-4 text-sm leading-6 text-warning">
                <p className="font-semibold">待你确认</p>
                <p className="mt-1">字幕已就绪。确认后会开始生成总结，也可以展开下方选项调整模型或邮件设置。</p>
              </div>
              <button type="button" onClick={startSummary} disabled={starting} className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-2xl bg-brand px-5 text-sm font-semibold text-white transition hover:brightness-105 active:scale-95 disabled:opacity-50">
                <Play size={17} />
                确认并总结
              </button>
              <button
                type="button"
                disabled={starting}
                onClick={async () => {
                  setActionError(null)
                  setStarting(true)
                  try {
                    await resumeJob(jobId, {...options, force_asr: true})
                    await refresh()
                  } catch (err) {
                    const message = err instanceof Error ? err.message : '重新转写失败'
                    setActionError(message)
                    toast.error('重新转写失败', message)
                  } finally {
                    setStarting(false)
                  }
                }}
                className="mt-2 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-2xl border border-line px-5 text-sm font-semibold text-muted transition hover:bg-lift active:scale-95 disabled:opacity-50"
              >
                重新走 ASR
              </button>
            </section>
          )}
          {canRetry && failure && (
            <section className="rounded-3xl bg-panel p-4 shadow-card">
              <div className="rounded-2xl bg-red-50 p-4 text-sm leading-6 text-danger">
                <p className="font-semibold">{failure.title}</p>
                <p className="mt-1">{failure.message}</p>
              </div>
              <button type="button" onClick={retry} disabled={starting} className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-2xl bg-brand px-5 text-sm font-semibold text-white transition hover:brightness-105 active:scale-95 disabled:opacity-50">
                <RotateCw size={17} />
                {failure.actionLabel || '重试任务'}
              </button>
            </section>
          )}
          <section className="rounded-3xl bg-panel p-4 shadow-card">
            <h2 className="text-sm font-semibold">资源</h2>
            <button type="button" onClick={downloadAudio} disabled={!job.audio_available} className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-40">
              <Download size={16} />
              下载音频
            </button>
            {audioPreviewUrl && (
              <audio controls src={audioPreviewUrl} className="mt-3 w-full" />
            )}
          </section>
          {canStartSummary && (
            <OptionsForm
              defaults={defaults}
              defaultsLoading={defaultsLoading}
              options={options}
              open={optionsOpen}
              onToggle={() => setOptionsOpen((value) => !value)}
              onChange={setOptions}
            />
          )}
        </aside>
        <div className="grid content-start gap-5">
          <SummaryView
            summary={job.summary}
            title={job.title}
            job={job}
            onCopy={() => toast.success('总结已复制')}
            onDownload={() => toast.success('Markdown 已开始下载')}
            onEmail={canResendEmail ? resend : undefined}
          />
          <TranscriptView job={job} onUpload={uploadTranscript} />
        </div>
      </div>
      {(canStartSummary || canCancel || canResendEmail || canRetry) && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-panel/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur md:hidden">
          <div className="mx-auto flex max-w-lg gap-2">
            {canStartSummary && (
              <button type="button" onClick={startSummary} disabled={starting} className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-2xl bg-brand px-5 text-sm font-semibold text-white transition active:scale-95 disabled:opacity-50">
                <Play size={17} />
                确认并总结
              </button>
            )}
            {canCancel && (
              <button type="button" onClick={cancel} className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition active:scale-95">
                <XCircle size={16} />
                取消
              </button>
            )}
            {canResendEmail && (
              <button type="button" onClick={resend} className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-2xl bg-brand px-4 text-sm font-semibold text-white transition active:scale-95">
                <Mail size={16} />
                重发邮件
              </button>
            )}
            {canRetry && (
              <button type="button" onClick={retry} disabled={starting} className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-2xl bg-brand px-4 text-sm font-semibold text-white transition active:scale-95 disabled:opacity-50">
                <RotateCw size={16} />
                重试
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
