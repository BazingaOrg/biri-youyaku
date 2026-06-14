import {Clipboard, X} from 'lucide-react'
import type React from 'react'
import {sanitizeBiliInput} from '../lib/biliUrl'

interface UrlInputProps {
  value: string
  loading: boolean
  error?: string | null
  actions?: React.ReactNode
  onChange: (value: string) => void
  onSubmit: () => void
}

export function UrlInput({value, loading, error, actions, onChange, onSubmit}: UrlInputProps) {
  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText()
      onChange(sanitizeBiliInput(text))
    } catch {
      // Clipboard permission errors are browser UI decisions; keep the input usable.
    }
  }

  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    const text = event.clipboardData.getData('text')
    if (!text) {
      return
    }
    // 始终 normalize：即使用户粘贴的就是「干净 URL」，也要剥掉 share_source / vd_source
    // 之类的追踪参数，避免它们进 DB 与 dedup hash。
    const cleaned = sanitizeBiliInput(text)
    if (cleaned && cleaned !== text) {
      event.preventDefault()
      onChange(cleaned)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      onSubmit()
    }
  }

  return (
    <>
      <div className="relative">
        <input
          id="bili-url"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onPaste={handlePaste}
          onKeyDown={handleKeyDown}
          placeholder="https://www.bilibili.com/video/BV..."
          disabled={loading}
          className="min-h-14 w-full rounded-2xl border border-line bg-panel px-5 pr-28 text-base outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-brand focus:shadow-[0_0_0_3px_var(--color-brand-soft)] disabled:opacity-60"
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
          {value && (
            <button type="button" aria-label="清除链接" onClick={() => onChange('')} className="grid h-10 w-10 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95">
              <X size={17} />
            </button>
          )}
          <button type="button" aria-label="粘贴链接" onClick={paste} className="grid h-10 w-10 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95">
            <Clipboard size={17} />
          </button>
        </div>
      </div>
      {actions}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </>
  )
}
