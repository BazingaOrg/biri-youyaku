import {useCallback, useEffect, useState} from 'react'
import {ArrowLeft, Download, Mail, MoreHorizontal, Play, RotateCw, XCircle} from 'lucide-react'
import {cancelJob, downloadJobAudio, resendEmail, resumeJob} from '../lib/api'
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

interface JobPageProps {
  jobId: string
  onBack: () => void
}

export function JobPage({jobId, onBack}: JobPageProps) {
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
  }, [jobId])

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
      toast.error(`${job.error_stage || '任务'} 失败`, job.error_message)
      setNotifiedError(job.error_message)
    }
  }, [job?.error_message, job?.error_stage, job?.options.email_enabled, job?.status, notifiedCompleted, notifiedError, toast])

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

  if (error) {
    return <p className="rounded-lg bg-red-50 p-4 text-danger">{error}</p>
  }

  if (!job) {
    return <div className="rounded-lg bg-panel p-6 text-muted shadow-surface">加载中</div>
  }

  const canCancel = ['PENDING', 'FETCHING_META', 'DOWNLOADING_AUDIO', 'TRANSCRIBING', 'SUMMARIZING', 'EMAILING'].includes(job.status)
  const canStartSummary = job.status === 'TRANSCRIPT_READY'
  const canResendEmail = job.status === 'COMPLETED' && Boolean(job.summary)

  return (
    <div className="grid gap-5">
      <button type="button" onClick={onBack} className="inline-flex min-h-10 w-fit items-center gap-2 rounded-lg px-1 text-muted transition-transform active:scale-95">
        <ArrowLeft size={18} />
        返回
      </button>
      <section className="rounded-3xl bg-panel p-4 shadow-bili">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-pink">{job.bvid || '等待元信息'}</p>
            <h1 className="mt-2 text-2xl font-semibold">{job.title || job.url}</h1>
            <p className="mt-2 text-sm text-muted">
              {job.author || '未知 UP'} · {formatDuration(job.duration)}
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {canStartSummary && (
              <button type="button" onClick={startSummary} disabled={starting} className="inline-flex min-h-11 items-center gap-2 rounded-full bg-pink px-5 text-sm font-semibold text-white shadow-bili transition hover:brightness-105 active:scale-95 disabled:opacity-50">
                <Play size={17} />
                开始总结
              </button>
            )}
            {canCancel && (
              <button type="button" onClick={cancel} className="inline-flex min-h-11 items-center gap-2 rounded-full bg-lift px-4 text-sm text-muted transition hover:bg-line/70 active:scale-95">
                <XCircle size={16} />
                取消
              </button>
            )}
            {canResendEmail && (
              <button type="button" onClick={resend} className="inline-flex min-h-11 items-center gap-2 rounded-full bg-pink px-4 text-sm font-medium text-white shadow-bili transition hover:brightness-105 active:scale-95">
                <Mail size={16} />
                重发邮件
              </button>
            )}
            <div className="relative">
              <button type="button" aria-label="更多操作" onClick={() => setMoreOpen((value) => !value)} className="grid h-11 w-11 place-items-center rounded-full bg-lift text-muted transition hover:bg-line/70 active:scale-95">
                <MoreHorizontal size={18} />
              </button>
              {moreOpen && (
                <div className="absolute right-0 top-12 z-10 grid min-w-36 gap-1 rounded-2xl bg-white p-2 shadow-bili">
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
        {job.error_message && (
          <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-danger">{job.error_stage}: {job.error_message}</p>
        )}
        {actionError && (
          <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-danger">{actionError}</p>
        )}
      </section>
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <JobProgress status={job.status} />
        <SummaryView
          summary={job.summary}
          title={job.title}
          onCopy={() => toast.success('总结已复制')}
          onDownload={() => toast.success('Markdown 已开始下载')}
        />
      </div>
      <TranscriptView job={job} />
      {canStartSummary && (
        <section className="grid gap-3">
          <OptionsForm
            defaults={defaults}
            defaultsLoading={defaultsLoading}
            options={options}
            open={optionsOpen}
            onToggle={() => setOptionsOpen((value) => !value)}
            onChange={setOptions}
          />
        </section>
      )}
    </div>
  )
}
