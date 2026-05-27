import {useState} from 'react'
import {FileText, History} from 'lucide-react'
import {createJob} from '../lib/api'
import {UrlInput} from '../components/UrlInput'
import {isValidBiliUrl} from '../lib/url'
import {useToast} from '../components/ToastProvider'

interface HomePageProps {
  onCreated: (jobId: string) => void
  onHistory: () => void
}

export function HomePage({onCreated, onHistory}: HomePageProps) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [urlError, setUrlError] = useState<string | null>(null)
  const toast = useToast()

  const submit = async () => {
    if (!isValidBiliUrl(url)) {
      setUrlError('请输入有效的 B 站视频链接（支持 BV 号、av 号或完整 URL）')
      return
    }
    setLoading(true)
    setError(null)
    setUrlError(null)
    try {
      const response = await createJob(url.trim(), {})
      onCreated(response.job_id)
    } catch (err) {
      const message = err instanceof Error ? err.message : '创建任务失败'
      setError(message)
      toast.error('创建任务失败', message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto grid min-h-[calc(100vh-4rem)] w-full max-w-3xl content-center gap-5">
      <UrlInput
        value={url}
        loading={loading}
        error={urlError}
        onChange={(nextUrl) => {
          setUrl(nextUrl)
          setUrlError(null)
        }}
        onSubmit={submit}
        actions={
          <>
            <p className="mt-3 text-center text-sm leading-6 text-muted">
              粘贴 B 站视频链接，先获取字幕或自动转录，确认后生成 Markdown 总结并可发送邮件。
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-3">
              <button
                type="button"
                disabled={loading || url.trim().length === 0}
                onClick={submit}
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-pink/70 bg-pink px-6 font-semibold text-white shadow-[0_10px_0_#d94f78,0_16px_28px_rgba(251,114,153,0.22)] transition hover:-translate-y-0.5 hover:brightness-105 active:translate-y-1 active:shadow-[0_4px_0_#d94f78,0_8px_18px_rgba(251,114,153,0.18)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <FileText size={18} />
                获取字幕
              </button>
              <button
                type="button"
                onClick={onHistory}
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-line bg-white px-6 font-semibold text-muted shadow-[0_10px_0_#e6dce5,0_16px_28px_rgba(24,25,28,0.08)] transition hover:-translate-y-0.5 hover:text-pink active:translate-y-1 active:shadow-[0_4px_0_#e6dce5,0_8px_18px_rgba(24,25,28,0.06)]"
              >
                <History size={18} />
                历史记录
              </button>
            </div>
          </>
        }
      />
      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-danger">{error}</p>}
    </div>
  )
}
