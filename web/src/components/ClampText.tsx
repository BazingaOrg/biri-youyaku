import {useEffect, useLayoutEffect, useRef, useState, type ReactNode} from 'react'
import {Link} from 'wouter'

function isClamped(el: HTMLElement) {
  const full = el.cloneNode(true)
  if (!(full instanceof HTMLElement)) return false
  full.style.position = 'absolute'
  full.style.visibility = 'hidden'
  full.style.pointerEvents = 'none'
  full.style.display = 'block'
  full.style.webkitLineClamp = 'unset'
  full.style.webkitBoxOrient = 'unset'
  full.style.overflow = 'visible'
  full.style.height = 'auto'
  full.style.maxHeight = 'none'
  full.style.width = `${el.clientWidth}px`
  el.parentElement?.appendChild(full)
  const overflow = full.scrollHeight - el.clientHeight > 1
  full.remove()
  return overflow
}

export function ClampText({
  text,
  className = '',
  href,
  external = false,
}: {
  text: string
  className?: string
  href?: string
  external?: boolean
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const [overflow, setOverflow] = useState(false)
  const [bubble, setBubble] = useState<{top: number; left: number; width: number} | null>(null)

  useLayoutEffect(() => {
    const el = boxRef.current?.firstElementChild
    if (!(el instanceof HTMLElement)) return
    const measure = () => setOverflow(isClamped(el))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [text, className, href])

  useEffect(() => {
    if (!bubble) return
    const hide = () => setBubble(null)
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [bubble])

  const show = () => {
    const el = boxRef.current
    if (!el || !overflow) return
    const rect = el.getBoundingClientRect()
    const width = Math.min(Math.max(rect.width, 280), 512, window.innerWidth - 32)
    const left = Math.max(16, Math.min(rect.left, window.innerWidth - 16 - width))
    setBubble({top: rect.bottom, left, width})
  }
  const hide = () => setBubble(null)

  const clamped = `block line-clamp-1 break-words ${className}`
  let body: ReactNode
  if (href && external) {
    body = (
      <a href={href} target="_blank" rel="noreferrer" className={clamped}>
        {text}
      </a>
    )
  } else if (href) {
    body = (
      <Link href={href} className={clamped}>
        {text}
      </Link>
    )
  } else {
    body = <p className={clamped}>{text}</p>
  }

  return (
    <div
      ref={boxRef}
      className="min-w-0"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {body}
      {bubble ? (
        <span
          role="tooltip"
          style={{top: bubble.top, left: bubble.left, width: bubble.width}}
          className="fixed z-30 pt-1.5"
        >
          <span className="block rounded-[12px] border border-line bg-panel px-3 py-2 text-left text-sm font-normal leading-snug break-words text-ink shadow-card">
            {text}
          </span>
        </span>
      ) : null}
    </div>
  )
}
