const face = '#FBF7F2'
const plate = 'var(--color-brand-solid)'

export function BrandMark({className = 'h-7 w-7'}: {className?: string}) {
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden>
      <rect x="16" y="16" width="480" height="480" rx="120" fill={plate} />
      <rect x="168" y="56" width="66" height="180" rx="33" fill={face} />
      <rect x="278" y="56" width="66" height="180" rx="33" fill={face} />
      <ellipse cx="256" cy="282" rx="124" ry="106" fill={face} />
      <g className="rabbit-blink">
        <circle cx="208" cy="262" r="22" fill={plate} />
        <circle cx="304" cy="262" r="22" fill={plate} />
      </g>
      <path d="M64 330 Q160 296 256 332 Q352 296 448 330 L448 452 Q352 420 256 456 Q160 420 64 452 Z" fill={face} stroke={plate} strokeWidth="24" strokeLinejoin="round" />
      <path d="M256 332 V456" stroke={plate} strokeWidth="18" />
    </svg>
  )
}
