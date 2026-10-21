export interface SegmentedOption<T extends string> {
  value: T
  label: string
  count?: number | string | null
}

interface SegmentedProps<T extends string> {
  value: T
  options: Array<SegmentedOption<T>>
  onChange: (value: T) => void
  ariaLabel?: string
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: SegmentedProps<T>) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="inline-flex max-w-full flex-wrap gap-0.5 rounded-xl bg-lift p-[3px]"
    >
      {options.map((option) => {
        const on = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(option.value)}
            className={`inline-flex min-h-8 items-center rounded-[9px] px-3 text-[13px] whitespace-nowrap transition-colors ${
              on ? 'bg-panel font-medium text-ink shadow-sm' : 'text-muted hover:text-ink'
            }`}
          >
            {option.label}
            {option.count != null && option.count !== '' ? (
              <span className="ml-1 tabular-nums text-muted/80">{option.count}</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
