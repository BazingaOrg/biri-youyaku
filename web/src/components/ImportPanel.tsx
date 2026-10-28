import {FileUp, Loader2, Square, X} from 'lucide-react'
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
    <section className="mt-3 rounded-[16px] border border-line bg-panel p-4 shadow-card" aria-label="导入文件">
      <div className="flex flex-wrap items-start gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-[11px] bg-brand-soft text-brand"><FileUp size={18} /></div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">导入音视频或字幕</p>
          <p className="mt-0.5 text-xs leading-5 text-muted">文件会上传到服务端处理；上传完成前请不要离开此页。</p>
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <label className="min-w-0">
          <span className="sr-only">选择文件</span>
          <input type="file" accept={accept} disabled={busy} onChange={(event) => choose(event.target.files?.[0] ?? null)} className="block w-full min-w-0 text-sm text-muted file:mr-3 file:rounded-[10px] file:border-0 file:bg-lift file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink hover:file:bg-brand-soft disabled:opacity-60" />
        </label>
        <label>
          <span className="sr-only">标题</span>
          <input value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder="可选标题" className="min-h-10 w-full rounded-[10px] border border-line bg-canvas px-3 text-sm outline-none placeholder:text-muted/55 focus:border-brand/60 disabled:opacity-60" />
        </label>
      </div>
      <label className="mt-2 block">
        <span className="sr-only">来源链接</span>
        <input value={sourceUrl} disabled={busy} onChange={(event) => setSourceUrl(event.target.value)} maxLength={2048} inputMode="url" placeholder="可选来源链接，用于回看原页面" className="min-h-10 w-full rounded-[10px] border border-line bg-canvas px-3 text-sm outline-none placeholder:text-muted/55 focus:border-brand/60 disabled:opacity-60" />
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <span>{allowed.map((item) => item.toUpperCase()).join(' · ')}</span>
        <span>上限 {displaySize(limit)}</span>
      </div>
      {capabilityError ? <div className="mt-2 flex items-center gap-2 text-xs text-warning"><span>暂时无法读取服务端能力，字幕导入仍可尝试。</span><button type="button" onClick={() => loadCapabilities()} className="underline underline-offset-2">重试</button></div> : null}
      {file ? <p className="mt-2 truncate text-xs text-ink" title={file.name}>{file.name} · {displaySize(file.size)}{isSubtitle ? ' · 字幕将直接生成笔记' : ''}</p> : null}
      {busy ? (
        <div className="mt-3" aria-live="polite">
          {progress != null ? <div className="h-1.5 overflow-hidden rounded-full bg-lift"><div className="h-full rounded-full bg-brandSolid transition-[width] duration-150 ease-out" style={{width: `${Math.max(3, progress * 100)}%`}} /></div> : null}
          <div className="mt-2 flex items-center justify-between gap-3 text-xs text-muted"><span className="inline-flex items-center gap-1.5"><Loader2 size={14} className="animate-spin" />{checking ? '服务端正在检查并创建任务…' : `正在上传${progress != null ? ` ${Math.round(progress * 100)}%` : ''}`}</span><Button variant="secondary" className="!min-h-8 !px-2.5 !text-xs" onClick={cancel}><Square size={12} />取消</Button></div>
        </div>
      ) : null}
      {error || sourceUrlError ? <div className="mt-3 flex items-start gap-2 text-sm text-danger"><X size={16} className="mt-0.5 shrink-0" /><span>{error || sourceUrlError}</span></div> : null}
      <div className="mt-3 flex justify-end"><Button variant="primary" disabled={!file || busy || Boolean(error || sourceUrlError)} onClick={submit}>导入并生成笔记</Button></div>
    </section>
  )
}
