interface UrlInputProps {
  value: string
  loading: boolean
  error?: string | null
  actions?: React.ReactNode
  onChange: (value: string) => void
  onSubmit: () => void
}

export function UrlInput({value, loading, error, actions, onChange, onSubmit}: UrlInputProps) {
  return (
    <>
      <input
        id="bili-url"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="https://www.bilibili.com/video/BV..."
        className="min-h-14 w-full rounded-2xl border border-pink/40 bg-white px-5 text-base outline-none shadow-pinkGlow transition-[box-shadow,border-color] placeholder:text-muted/55 focus:border-pink/70 focus:shadow-pinkGlowStrong motion-safe:animate-glowPulse"
      />
      {actions}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </>
  )
}
