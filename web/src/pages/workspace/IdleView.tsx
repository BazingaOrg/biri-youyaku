import {useState} from 'react'
import {BookOpen, History, RotateCw, Sparkles} from 'lucide-react'
import {UrlInput} from '../../components/UrlInput'
import {isValidBiliUrl, sanitizeBiliInput} from '../../lib/biliUrl'

interface IdleViewProps {
  onSubmit: (url: string) => Promise<void>
  onOpenHistory: () => void
  onOpenKnowledge: () => void
}

/** 空闲态：粘 URL → 校验 → 提交。任何已识别为「在飞 / 历史」的视图都不走这里。 */
export function IdleView({onSubmit, onOpenHistory, onOpenKnowledge}: IdleViewProps) {
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
      <div className="grid w-full max-w-xl gap-7">
        <header className="grid justify-items-center gap-3 text-center">
          <img src="/icon.svg" alt="" aria-hidden className="h-14 w-14" />
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink sm:text-3xl">
              biri-youyaku
            </h1>
            <p className="mt-1 text-sm leading-6 text-muted sm:text-base">
              粘贴 B 站链接，生成笔记与可跳转字幕
            </p>
          </div>
        </header>

        <div className="grid gap-3">
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
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || url.trim().length === 0}
            className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-brandSolid px-5 text-sm font-medium text-onBrand shadow-card transition-[transform,filter] duration-150 ease-out hover:brightness-105 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? <RotateCw size={18} className="animate-spin" /> : <Sparkles size={18} />}
            {busy ? '正在创建总结…' : '开始总结'}
          </button>
        </div>

        <nav aria-label="快捷入口" className="flex flex-wrap items-center justify-center gap-2">
          <button
            type="button"
            onClick={onOpenHistory}
            className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition-[transform,background-color,color] duration-150 ease-out hover:bg-line/70 hover:text-ink active:scale-[0.97]"
          >
            <History size={17} />
            历史记录
          </button>
          <button
            type="button"
            onClick={onOpenKnowledge}
            className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-lift px-4 text-sm text-muted transition-[transform,background-color,color] duration-150 ease-out hover:bg-line/70 hover:text-ink active:scale-[0.97]"
          >
            <BookOpen size={17} />
            知识库
          </button>
        </nav>
      </div>
    </div>
  )
}
