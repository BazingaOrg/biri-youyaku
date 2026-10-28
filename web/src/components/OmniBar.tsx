import {Link, Search, X} from 'lucide-react'
import {useEffect, type FormEvent} from 'react'
import {Button} from './Button'
import {formatSavedDay} from '../lib/format'
import type {PasteAction} from '../lib/pasteAction'

interface OmniBarProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  action: PasteAction
  busy?: boolean
  hint?: boolean
  onRead?: (documentId: string) => void
  onRestore?: (documentId: string) => void
  onGenerate?: () => void
  onClear?: () => void
  sourceState?: 'idle' | 'resolving' | 'error'
  activeJobId?: string | null
}

export function OmniBar({
  value,
  onChange,
  onSubmit,
  action,
  busy = false,
  hint = true,
  onRead,
  onRestore,
  onGenerate,
  onClear,
  sourceState = 'idle',
  activeJobId = null,
}: OmniBarProps) {
  const isLink = action.kind !== 'text'
  const showGenerate = action.primary === 'generate'

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (target instanceof HTMLElement && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return
      }
      event.preventDefault()
      document.getElementById('omni')?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit()
  }

  return (
    <form className="mt-4 sm:mt-6" onSubmit={handleSubmit} role="search">
      <label htmlFor="omni" className="sr-only">
        粘贴视频链接或搜索笔记
      </label>
      <div className="flex min-h-14 items-center gap-2 rounded-[18px] border border-line bg-panel py-1.5 pl-4 pr-1.5 shadow-card focus-within:border-brand/40">
        <span className="flex text-muted/70" aria-hidden>
          {isLink ? <Link size={20} /> : <Search size={20} />}
        </span>
        <input
          id="omni"
          type="search"
          enterKeyHint={isLink ? 'go' : 'search'}
          autoComplete="off"
          value={value}
          disabled={busy}
          placeholder="粘贴 B 站或 YouTube 链接，或搜索已保存的内容"
          onChange={(event) => onChange(event.target.value)}
          className="min-h-11 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted/55 disabled:opacity-60"
        />
        {value ? (
          <button
            type="button"
            aria-label="清空"
            onClick={() => {
              onChange('')
              onClear?.()
            }}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-[10px] text-muted hover:bg-lift hover:text-ink"
          >
            <X size={16} />
          </button>
        ) : null}
        {showGenerate ? (
          <Button
            type="submit"
            variant="primary"
            className="hidden shrink-0 sm:inline-flex"
            disabled={busy}
          >
            {activeJobId ? '查看任务' : '生成笔记'}
          </Button>
        ) : null}
      </div>
      {action.kind === 'trashed' && action.trashed ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-3 rounded-[14px] border border-line bg-panel px-4 py-3.5">
          <div className="min-w-0 flex-1 basis-[260px]">
            <p className="text-xs text-muted">
              这个视频的笔记在最近删除里
              {action.trashed.daysLeft != null ? ` · ${action.trashed.daysLeft} 天后永久删除` : ''}
            </p>
            <p className="font-semibold break-words">{action.trashed.title}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={onGenerate} disabled={busy}>
              重新生成
            </Button>
            <Button
              variant="primary"
              onClick={() => action.trashed && onRestore?.(action.trashed.documentId)}
              disabled={busy}
            >
              恢复笔记
            </Button>
          </div>
        </div>
      ) : null}
      {action.kind === 'existing' && action.existing ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-3 rounded-[14px] border border-line bg-panel px-4 py-3.5">
          <div className="min-w-0 flex-1 basis-[260px]">
            <p className="text-xs text-muted">
              这个视频已经有笔记
              {action.existing.savedAt ? ` · ${formatSavedDay(action.existing.savedAt)} 保存` : ''}
            </p>
            <p className="font-semibold break-words">{action.existing.title}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={onGenerate} disabled={busy}>
              重新生成
            </Button>
            <Button variant="primary" onClick={() => action.existing && onRead?.(action.existing.documentId)}>
              阅读笔记
            </Button>
          </div>
        </div>
      ) : null}
      {action.kind === 'new-link' ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-3 rounded-[14px] border border-line bg-panel px-4 py-3.5">
          <div className="min-w-0 flex-1 basis-[260px]">
            <p className="text-xs text-muted">识别到支持的视频来源</p>
            <p className="font-semibold break-words">{activeJobId ? '这条内容正在处理，可以查看任务进度' : '生成后会出现在列表顶部，可以离开页面'}</p>
          </div>
          <div className="flex w-full sm:hidden">
            <Button type="submit" variant="primary" className="ml-auto" disabled={busy}>
              {activeJobId ? '查看任务' : '生成笔记'}
            </Button>
          </div>
        </div>
      ) : null}
      {isLink && sourceState === 'resolving' ? <p className="mt-2 px-1 text-xs text-muted" aria-live="polite">正在检查来源与已有笔记…</p> : null}
      {isLink && sourceState === 'error' ? <p className="mt-2 px-1 text-xs text-warning" aria-live="polite">暂时无法检查已有内容；提交时服务端会再次确认。</p> : null}
      {hint && !value ? (
        <p className="mt-2 flex items-baseline justify-between gap-3 px-1 text-[13px] text-muted">
          <span>可搜标题、UP 主、BV 号、标签、笔记正文和字幕</span>
          <span className="hidden shrink-0 sm:inline">
            按 <kbd>/</kbd> 聚焦 · <kbd>Enter</kbd> 搜索
          </span>
        </p>
      ) : null}
    </form>
  )
}
