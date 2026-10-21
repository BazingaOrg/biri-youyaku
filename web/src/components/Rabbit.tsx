import type {ReactNode} from 'react'

export type RabbitMood = 'asleep' | 'search' | 'wave' | 'error' | 'loading'

const paper = 'var(--color-bg-elevated)'
const ink = 'var(--color-brand-solid)'
const soft = 'var(--color-brand-soft)'
const line = 'var(--color-fg-muted)'

function Book({paws}: {paws: 'rest' | 'up'}) {
  const paw = paws === 'up'
    ? {body: 'M134 302 Q134 262 166 262 Q198 262 198 302 Z', twin: 'M314 302 Q314 262 346 262 Q378 262 378 302 Z', marks: 'M156 278 V294 M176 278 V294 M336 278 V294 M356 278 V294'}
    : {body: 'M134 330 Q134 290 166 290 Q198 290 198 330 Z', twin: 'M314 330 Q314 290 346 290 Q378 290 378 330 Z', marks: 'M156 306 V322 M176 306 V322 M336 306 V322 M356 306 V322'}
  return (
    <>
      <path d="M72 320 Q164 288 256 322 Q348 288 440 320 L440 444 Q348 414 256 448 Q164 414 72 444 Z" fill={paper} stroke={ink} strokeWidth="14" strokeLinejoin="round" />
      <path d="M256 322 V448" stroke={ink} strokeWidth="10" />
      <path d="M112 360 Q172 342 226 362 M112 396 Q172 378 226 398 M286 362 Q340 342 400 360 M286 398 Q340 378 400 396" stroke={line} strokeWidth="10" fill="none" strokeLinecap="round" />
      <path d={paw.body} fill={paper} stroke={ink} strokeWidth="10" strokeLinejoin="round" />
      <path d={paw.twin} fill={paper} stroke={ink} strokeWidth="10" strokeLinejoin="round" />
      <path d={paw.marks} stroke={soft} strokeWidth="7" strokeLinecap="round" />
    </>
  )
}

function Head({mood}: {mood: RabbitMood}) {
  const blink = mood === 'wave' || mood === 'loading'
  return (
    <g className={mood === 'loading' ? 'rabbit-peek' : undefined}>
      <rect x="178" y="72" width="54" height="160" rx="27" fill={paper} />
      <rect x="280" y="72" width="54" height="160" rx="27" fill={paper} />
      <rect x="194" y="96" width="22" height="104" rx="11" fill={ink} opacity="0.28" />
      <rect x="296" y="96" width="22" height="104" rx="11" fill={ink} opacity="0.28" />
      <ellipse cx="256" cy="282" rx="116" ry="100" fill={paper} />
      {mood === 'asleep' ? (
        <>
          <path d="M196 268 Q212 254 228 268" stroke={ink} strokeWidth="8" fill="none" strokeLinecap="round" />
          <path d="M284 268 Q300 254 316 268" stroke={ink} strokeWidth="8" fill="none" strokeLinecap="round" />
          <path d="M236 292 Q256 306 276 292" stroke={ink} strokeWidth="8" fill="none" strokeLinecap="round" />
        </>
      ) : null}
      {mood === 'search' ? (
        <>
          <ellipse cx="212" cy="262" rx="16" ry="10" fill={ink} />
          <ellipse cx="300" cy="262" rx="16" ry="10" fill={ink} />
        </>
      ) : null}
      {mood === 'error' ? (
        <>
          <path d="M190 236 L224 250" stroke={ink} strokeWidth="8" strokeLinecap="round" />
          <path d="M322 236 L288 250" stroke={ink} strokeWidth="8" strokeLinecap="round" />
          <circle cx="212" cy="270" r="16" fill={ink} />
          <circle cx="300" cy="270" r="16" fill={ink} />
          <path d="M232 300 Q256 286 280 300" stroke={ink} strokeWidth="8" fill="none" strokeLinecap="round" />
        </>
      ) : null}
      {mood === 'wave' || mood === 'loading' ? (
        <g className={blink ? 'rabbit-blink' : undefined}>
          <circle cx="212" cy="264" r="15" fill={ink} />
          <circle cx="300" cy="264" r="15" fill={ink} />
        </g>
      ) : null}
      {mood === 'wave' ? <path d="M236 300 Q256 314 276 300" stroke={ink} strokeWidth="8" fill="none" strokeLinecap="round" /> : null}
      {mood === 'loading' ? <path d="M244 292 L268 292 L256 304 Z" fill={soft} /> : null}
    </g>
  )
}

export function Rabbit({mood, className = 'h-32 w-32'}: {mood: RabbitMood; className?: string}) {
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden>
      <Head mood={mood} />
      <Book paws={mood === 'wave' ? 'up' : 'rest'} />
    </svg>
  )
}

export function RabbitScene({
  mood,
  title,
  children,
}: {
  mood: RabbitMood
  title?: string
  children?: ReactNode
}) {
  return (
    <div className="grid justify-items-center gap-3 py-12 text-center">
      <Rabbit mood={mood} />
      {title ? <h2 className="text-[17px] font-semibold text-ink">{title}</h2> : null}
      {children}
    </div>
  )
}
