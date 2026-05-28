import {useEffect, useState} from 'react'
import {Download, FileText, History, Mail, Play, RotateCcw} from 'lucide-react'
import {Link} from 'wouter'
import {createJob, listJobs, previewJob} from '../lib/api'
import type {Job, JobOptionOverrides} from '../lib/api'
import {UrlInput} from '../components/UrlInput'
import {isValidBiliUrl} from '../lib/url'
import {useToast} from '../components/ToastProvider'
import {formatDuration, formatStatus} from '../lib/format'
import {useShortcuts} from '../hooks/useShortcuts'

interface HomePageProps {
  onCreated: (jobId: string) => void
}

export function HomePage({onCreated}: HomePageProps) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof previewJob>>['meta'] | null>(null)
  const [recentJobs, setRecentJobs] = useState<Job[]>([])
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [options, setOptions] = useState<JobOptionOverrides>({task_type: 'summary'})
  const [error, setError] = useState<string | null>(null)
  const [urlError, setUrlError] = useState<string | null>(null)
  const toast = useToast()

  const pasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      setUrl(text)
      setPreview(null)
      setUrlError(null)
    } catch {
      toast.error('读取剪贴板失败', '请手动粘贴链接。')
    }
  }

  useEffect(() => {
    listJobs({limit: 6})
      .then((response) => setRecentJobs(response.jobs))
      .catch(() => setRecentJobs([]))
  }, [])

  const runPreview = async () => {
    if (!isValidBiliUrl(url)) {
      setUrlError('请输入有效的 B 站视频链接（支持 BV 号、av 号或完整 URL）')
      return
    }
    setPreviewLoading(true)
    setUrlError(null)
    try {
      const response = await previewJob(url.trim())
      setPreview(response.meta)
      if (response.dedup_job_id) {
        toast.info('已有相同视频任务', '可以直接打开历史任务，也可以继续重新创建。')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '预检失败'
      setUrlError(message)
    } finally {
      setPreviewLoading(false)
    }
  }

  const submit = async (extraOptions: JobOptionOverrides = {}) => {
    if (!isValidBiliUrl(url)) {
      setUrlError('请输入有效的 B 站视频链接（支持 BV 号、av 号或完整 URL）')
      return
    }
    setLoading(true)
    setError(null)
    setUrlError(null)
    try {
      const response = await createJob(url.trim(), {...options, ...extraOptions})
      toast.success('任务已创建')
      onCreated(response.job_id)
    } catch (err) {
      const message = err instanceof Error ? err.message : '创建任务失败'
      setError(message)
      toast.error('创建任务失败', message)
    } finally {
      setLoading(false)
    }
  }

  useShortcuts({
    onPaste: pasteFromClipboard,
    onSubmit: () => { preview ? void submit() : void runPreview() },
    onFocusSearch: () => document.getElementById('bili-url')?.focus(),
  })

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-6 py-4 sm:py-10">
      <section className="grid gap-5 rounded-3xl bg-panel p-5 shadow-card sm:p-8">
        <div className="grid gap-2">
          <h1 className="text-3xl font-semibold leading-tight sm:text-4xl">粘贴 B 站链接，要約一下</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted">先识别视频和字幕，再生成 Markdown 总结。桌面端回车即可预检，Cmd/Ctrl+Enter 直接开始。</p>
        </div>
        <UrlInput
          value={url}
          loading={loading || previewLoading}
          error={urlError}
          onChange={(nextUrl) => {
            setUrl(nextUrl)
            setPreview(null)
            setUrlError(null)
          }}
          onSubmit={preview ? submit : runPreview}
        />
        {preview && (
          <div className="grid gap-1 rounded-2xl bg-lift p-4">
            <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted">
              <span className="rounded-full bg-brandSoft px-2.5 py-1 text-brand">{preview.bvid}</span>
              <span>{preview.has_subtitle ? '官方字幕可用' : '需要 ASR 转写'}</span>
              <span>{formatDuration(preview.duration)}</span>
            </div>
            <p className="line-clamp-2 font-semibold">{preview.title}</p>
            <p className="text-sm text-muted">{preview.author || '未知 UP'}</p>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={loading || previewLoading || url.trim().length === 0}
            onClick={() => { preview ? void submit() : void runPreview() }}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-brand px-5 text-sm font-semibold text-white transition hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Play size={17} />
            {preview ? '开始' : previewLoading ? '预检中...' : '预检链接'}
          </button>
          <button
            type="button"
            disabled={loading || url.trim().length === 0}
            onClick={() => {
              void submit({task_type: 'audio'})
            }}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl border border-line bg-panel px-5 text-sm font-semibold text-muted transition hover:bg-lift hover:text-ink active:scale-95 disabled:opacity-50"
          >
            <Download size={17} />
            仅下载音频
          </button>
          <button
            type="button"
            onClick={() => setOptionsOpen((value) => !value)}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl px-3 text-sm font-medium text-muted transition hover:bg-lift hover:text-ink active:scale-95"
          >
            <RotateCcw size={16} />
            更多选项
          </button>
        </div>
        {optionsOpen && (
          <div className="grid gap-3 rounded-2xl bg-lift p-3 sm:grid-cols-3">
            <label className="flex min-h-11 items-center gap-3 rounded-xl bg-panel px-3 text-sm">
              <input type="checkbox" checked={Boolean(options.force_asr)} onChange={(event) => setOptions((current) => ({...current, force_asr: event.target.checked}))} className="h-4 w-4 accent-brand" />
              强制 ASR
            </label>
            <label className="flex min-h-11 items-center gap-3 rounded-xl bg-panel px-3 text-sm">
              <input type="checkbox" checked={options.email_enabled !== false} onChange={(event) => setOptions((current) => ({...current, email_enabled: event.target.checked}))} className="h-4 w-4 accent-brand" />
              <Mail size={15} className="text-brand" />
              完成后邮件
            </label>
            <input value={options.llm_model ?? ''} onChange={(event) => setOptions((current) => ({...current, llm_model: event.target.value || undefined}))} placeholder="模型：使用后端默认" className="min-h-11 rounded-xl bg-panel px-3 text-sm outline-none focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />
          </div>
        )}
      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-danger">{error}</p>}
      </section>
      <section className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold">最近任务</h2>
          <Link href="/history" className="inline-flex min-h-10 items-center gap-2 rounded-xl px-3 text-sm text-muted transition hover:bg-lift hover:text-ink active:scale-95">
            <History size={16} />
            全部历史
          </Link>
        </div>
        {recentJobs.length > 0 ? (
          <div className="flex snap-x gap-3 overflow-x-auto pb-2">
            {recentJobs.map((job) => (
              <Link key={job.id} href={`/jobs/${job.id}`} className="grid min-h-32 w-64 shrink-0 snap-start content-between rounded-2xl bg-panel p-4 shadow-card transition hover:-translate-y-0.5 hover:shadow-cardHover active:scale-[0.99]">
                <span className="line-clamp-2 text-sm font-semibold">{job.title || job.url}</span>
                <span className="mt-4 flex items-center justify-between gap-3 text-xs text-muted">
                  <span className="truncate">{job.author || '未知 UP'}</span>
                  <span className="rounded-full bg-brandSoft px-2.5 py-1 text-brand">{formatStatus(job.status)}</span>
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl bg-panel p-6 text-sm text-muted shadow-card">暂无历史任务。粘贴一个链接开始。</div>
        )}
      </section>
    </div>
  )
}
