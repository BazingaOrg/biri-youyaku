import {useState} from 'react'
import {BarChart3, History, RotateCw, Sparkles, Users} from 'lucide-react'
import {Link} from 'wouter'
import {IconButton} from '../../components/IconButton'
import {UrlInput} from '../../components/UrlInput'
import {isValidBiliUrl, sanitizeBiliInput} from '../../lib/biliUrl'

interface IdleViewProps {
  onSubmit: (url: string) => Promise<void>
  onOpenHistory: () => void
}

/** 空闲态：粘 URL → 校验 → 提交。任何已识别为「在飞 / 历史」的视图都不走这里。 */
export function IdleView({onSubmit, onOpenHistory}: IdleViewProps) {
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
        <Link
          href="/up"
          className="inline-flex items-center justify-center gap-1.5 text-xs text-muted underline-offset-2 transition hover:text-brand hover:underline"
        >
          <Users size={13} />
          或按 UP 主浏览投稿
        </Link>
        <Link
          href="/stats"
          className="inline-flex items-center justify-center gap-1.5 text-xs text-muted underline-offset-2 transition hover:text-brand hover:underline"
        >
          <BarChart3 size={13} />
          查看统计
        </Link>
      </div>
    </div>
  )
}
