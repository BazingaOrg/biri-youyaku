import {ChevronDown, FileUp, Loader2, Square, X} from 'lucide-react'
import {useEffect, useRef, useState} from 'react'
import {getSourceCapabilities, uploadImport, type SourceCapabilities} from '../lib/api'
import {Button} from './Button'
import {sourceHref} from '../lib/sourceUrl'

interface ImportPanelProps {
  onAccepted: (jobId: string, deduped: boolean) => void
  onBusyChange?: (busy: boolean) => void
}

function displaySize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.ceil(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`
}

function suffix(file: File | null) {
  return file?.name.split('.').pop()?.toLowerCase() ?? ''
}

export function ImportPanel({onAccepted, onBusyChange}: ImportPanelProps) {
  const [capabilities, setCapabilities] = useState<SourceCapabilities | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [capabilityError, setCapabilityError] = useState(false)
  const abortRef = useRef<(() => void) | null>(null)
  const isSubtitle = ['srt', 'vtt'].includes(suffix(file))
  const busy = progress != null || checking

  useEffect(() => {
    onBusyChange?.(busy)
  }, [busy, onBusyChange])

  const loadCapabilities = () => {
    const controller = new AbortController()
    setCapabilityError(false)
    void getSourceCapabilities({signal: controller.signal}).then(setCapabilities).catch(() => {
      if (!controller.signal.aborted) setCapabilityError(true)
    })
    return controller
  }

  useEffect(() => {
    const controller = loadCapabilities()
    return () => controller.abort()
  }, [])

  useEffect(() => () => abortRef.current?.(), [])

  useEffect(() => {
    if (!busy) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [busy])

  const limit = capabilities?.upload.max_bytes ?? 80 * 1024 * 1024
  const allowed = (capabilities?.upload.extensions ?? ['mp3', 'm4a', 'wav', 'flac', 'ogg', 'mp4', 'mov', 'mkv', 'webm', 'srt', 'vtt']).map((item) => item.replace(/^\./, ''))
  const mediaAvailable = Boolean(capabilities?.ffmpeg && capabilities?.ffprobe && capabilities?.asr.installed)

  const choose = (next: File | null) => {
    setError(null)
    setFile(next)
    if (!next) return
    if (!allowed.includes(suffix(next))) setError('请选择支持的音视频或字幕文件')
    else if (next.size > limit) setError(`文件超过 ${displaySize(limit)} 上限`)
    else if (!['srt', 'vtt'].includes(suffix(next)) && capabilities && !mediaAvailable) setError('服务器暂未就绪，音视频导入需要 ffmpeg、ffprobe 和 ASR')
  }

  const sourceUrlError = sourceUrl.trim() && !sourceHref(sourceUrl) ? '来源链接需为不含账号信息的 http/https 地址' : null

  const submit = () => {
    if (!file || busy || error || sourceUrlError) return
    const task = uploadImport(file, title, (loaded, total) => {
      const next = total ? loaded / total : 0
      setProgress(next)
      if (next >= 1) setChecking(true)
    }, sourceUrl)
    abortRef.current = task.abort
    setProgress(0)
    void task.promise
      .then((response) => {
        setProgress(null)
        setChecking(false)
        setFile(null)
        setTitle('')
        setSourceUrl('')
        onAccepted(response.job_id, Boolean(response.deduped))
      })
      .catch((reason: unknown) => {
        setProgress(null)
        setChecking(false)
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof Error ? reason.message : '导入失败，请重试')
      })
      .finally(() => {
        abortRef.current = null
      })
  }

  const cancel = () => abortRef.current?.()
  const accept = allowed.map((item) => `.${item}`).join(',')

  return (
    <section className="rounded-[16px] border border-line bg-panel p-4 shadow-card" aria-label="导入文件">
      <div className="flex flex-wrap items-start gap-3 pr-10">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-[11px] bg-brand-soft text-brand"><FileUp size={18} /></div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">导入音视频或字幕</p>
          <p className="mt-0.5 text-xs leading-5 text-muted">音视频将转写后总结，字幕可直接生成笔记。</p>
        </div>
      </div>
      <label className="mt-4 flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-[14px] border border-dashed border-line bg-canvas/60 px-4 py-5 text-center transition-colors focus-within:border-brand/60 focus-within:ring-2 focus-within:ring-brand/15 hover:border-brand/50 hover:bg-brand-soft/30">
        <input autoFocus type="file" aria-label="选择音视频或字幕文件" accept={accept} disabled={busy} onChange={(event) => choose(event.target.files?.[0] ?? null)} className="sr-only" />
        <span className="grid h-9 w-9 place-items-center rounded-[11px] bg-lift text-muted"><FileUp size={18} /></span>
        <span className="mt-2 text-sm font-medium text-ink">{file ? '更换文件' : '选择音视频或字幕文件'}</span>
        <span className="mt-1 text-xs leading-5 text-muted" title={allowed.map((item) => item.toUpperCase()).join(' · ')}>常见音视频、SRT / VTT 字幕 · 上限 {displaySize(limit)}</span>
      </label>
      {file ? <p className="mt-2 truncate text-xs text-ink" title={file.name}>{file.name} · {displaySize(file.size)}{isSubtitle ? ' · 字幕将直接生成笔记' : ''}</p> : null}
      {capabilityError ? <div className="mt-3 flex items-center gap-2 text-xs text-warning"><span>暂时无法读取服务端能力，字幕导入仍可尝试。</span><button type="button" onClick={() => loadCapabilities()} className="underline underline-offset-2">重试</button></div> : null}
      <details className="group mt-3">
        <summary className="flex min-h-10 w-fit cursor-pointer list-none items-center gap-1.5 rounded-[10px] text-[13px] font-medium text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
          <ChevronDown size={14} className="transition-transform group-open:rotate-180" />
          添加标题和来源链接（可选）
        </summary>
        <div className="mt-1 grid gap-3 sm:grid-cols-2">
          <label className="min-w-0 text-xs text-muted">
            标题
            <input value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder="可选标题" className="mt-1.5 min-h-10 w-full rounded-[10px] border border-line bg-canvas px-3 text-sm text-ink outline-none placeholder:text-muted/55 focus:border-brand/60 disabled:opacity-60" />
          </label>
          <label className="min-w-0 text-xs text-muted">
            来源链接
            <input value={sourceUrl} disabled={busy} onChange={(event) => setSourceUrl(event.target.value)} maxLength={2048} inputMode="url" placeholder="用于回看原页面" className="mt-1.5 min-h-10 w-full rounded-[10px] border border-line bg-canvas px-3 text-sm text-ink outline-none placeholder:text-muted/55 focus:border-brand/60 disabled:opacity-60" />
          </label>
        </div>
      </details>
      {busy ? (
        <div className="mt-3" aria-live="polite">
          {progress != null ? <div className="h-1.5 overflow-hidden rounded-full bg-lift"><div className="h-full rounded-full bg-brandSolid transition-[width] duration-150 ease-out" style={{width: `${Math.max(3, progress * 100)}%`}} /></div> : null}
          <div className="mt-2 flex items-center justify-between gap-3 text-xs text-muted"><span className="inline-flex items-center gap-1.5"><Loader2 size={14} className="animate-spin" />{checking ? '服务端正在检查并创建任务…' : `正在上传${progress != null ? ` ${Math.round(progress * 100)}%` : ''}`}</span><Button variant="secondary" className="!min-h-8 !px-2.5 !text-xs" onClick={cancel}><Square size={12} />取消</Button></div>
          <p className="mt-2 text-xs text-warning">上传及服务端检查完成前，请不要离开此页。</p>
        </div>
      ) : null}
      {error || sourceUrlError ? <div role="alert" className="mt-3 flex items-start gap-2 text-sm text-danger"><X size={16} className="mt-0.5 shrink-0" /><span>{error || sourceUrlError}</span></div> : null}
      <div className="mt-4 flex justify-end"><Button variant="primary" className="!w-full sm:!w-auto" disabled={!file || busy || Boolean(error || sourceUrlError)} onClick={submit}>导入并生成笔记</Button></div>
    </section>
  )
}
