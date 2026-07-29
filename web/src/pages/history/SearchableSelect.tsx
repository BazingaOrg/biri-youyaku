import {Check, ChevronDown, Search} from 'lucide-react'
import {useEffect, useRef, useState} from 'react'

export interface SearchableSelectItem {
  key: string
  label: string
  count: number
}

export function SearchableSelect({
  ariaLabel,
  placeholder,
  items,
  value,
  onChange,
  tag = false,
}: {
  ariaLabel: string
  placeholder: string
  items: SearchableSelectItem[]
  value: string | null
  onChange: (value: string | null) => void
  tag?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const selected = items.find((item) => item.key === value)
  // Keep orphan values visible so an active filter never falls back to “全部…”.
  const displayLabel = selected
    ? `${tag ? '#' : ''}${selected.label}`
    : value
      ? `${tag ? '#' : ''}${value}`
      : null
  const hasValue = value != null
  const filtered = items.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase()))

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return
      setOpen(false)
    }
    window.addEventListener('mousedown', onPointerDown)
    return () => window.removeEventListener('mousedown', onPointerDown)
  }, [open])

  useEffect(() => {
    if (!open) return
    setQuery('')
    window.setTimeout(() => inputRef.current?.focus(), 0)
  }, [open])

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((current) => !current)}
        className={`flex min-h-11 w-full items-center gap-2 rounded-2xl bg-lift px-3 text-left text-sm transition-[background-color,color] hover:bg-line/70 ${
          hasValue ? 'text-ink' : 'text-muted'
        }`}
      >
        <span className="min-w-0 flex-1 truncate">{displayLabel ?? placeholder}</span>
        <ChevronDown size={15} className="shrink-0" />
      </button>
      {open && (
        <div className="absolute z-30 mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-line bg-panel p-2 shadow-cardHover">
          <label className="relative block">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`搜索${ariaLabel}`}
              className="min-h-10 w-full rounded-xl bg-lift py-2 pl-9 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30"
            />
          </label>
          <div role="listbox" aria-label={ariaLabel} className="mt-2 max-h-64 overflow-y-auto">
            <button
              type="button"
              role="option"
              aria-selected={value == null}
              onClick={() => {
                onChange(null)
                setOpen(false)
              }}
              className="flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-left text-sm text-muted hover:bg-lift hover:text-ink"
            >
              <span className="min-w-0 flex-1">全部</span>
              {value == null && <Check size={15} className="text-brand" />}
            </button>
            {hasValue && !selected && (
              <button
                type="button"
                role="option"
                aria-selected
                onClick={() => setOpen(false)}
                className="flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-left text-sm text-ink hover:bg-lift"
              >
                <span className="min-w-0 flex-1 truncate">{displayLabel}</span>
                <Check size={15} className="text-brand" />
              </button>
            )}
            {filtered.map((item) => (
              <button
                key={item.key}
                type="button"
                role="option"
                aria-selected={value === item.key}
                onClick={() => {
                  onChange(item.key)
                  setOpen(false)
                }}
                className="flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-left text-sm text-muted hover:bg-lift hover:text-ink"
              >
                <span className="min-w-0 flex-1 truncate">{tag ? '#' : ''}{item.label}</span>
                <span className="text-xs text-muted">{item.count}</span>
                {value === item.key && <Check size={15} className="text-brand" />}
              </button>
            ))}
            {filtered.length === 0 && !hasValue && <p className="px-3 py-5 text-center text-sm text-muted">没有匹配项</p>}
            {filtered.length === 0 && hasValue && selected && <p className="px-3 py-5 text-center text-sm text-muted">没有匹配项</p>}
          </div>
        </div>
      )}
    </div>
  )
}
