import {useEffect, useLayoutEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode} from 'react'
import {Link} from 'wouter'

const BUBBLE_GAP = 12
const BUBBLE_MARGIN = 8

function placeBubble(tip: HTMLElement, caret: HTMLElement, x: number, y: number) {
  const maxWidth = Math.min(320, window.innerWidth - BUBBLE_MARGIN * 2)
  tip.style.maxWidth = `${maxWidth}px`
  const {width, height} = tip.getBoundingClientRect()
  const space = {
    below: window.innerHeight - y - BUBBLE_GAP - BUBBLE_MARGIN,
    above: y - BUBBLE_GAP - BUBBLE_MARGIN,
    right: window.innerWidth - x - BUBBLE_GAP - BUBBLE_MARGIN,
    left: x - BUBBLE_GAP - BUBBLE_MARGIN,
  }
  const verticalRoom = Math.max(space.above, space.below)
  const horizontalRoom = Math.max(space.left, space.right)
  const vertical = verticalRoom >= height || verticalRoom >= horizontalRoom
  let top = y
  let left = x
  let side: 'below' | 'above' | 'right' | 'left' = 'below'
  if (vertical) {
    side = space.below >= height || space.below >= space.above ? 'below' : 'above'
    top = side === 'below' ? y + BUBBLE_GAP : y - BUBBLE_GAP - height
    left = x - 28
  } else {
    side = space.right >= width || space.right >= space.left ? 'right' : 'left'
    left = side === 'right' ? x + BUBBLE_GAP : x - BUBBLE_GAP - width
    top = y - 18
  }
  top = Math.max(BUBBLE_MARGIN, Math.min(top, window.innerHeight - BUBBLE_MARGIN - height))
  left = Math.max(BUBBLE_MARGIN, Math.min(left, window.innerWidth - BUBBLE_MARGIN - width))
  tip.style.top = `${top}px`
  tip.style.left = `${left}px`
  const alongX = side === 'below' || side === 'above'
  const caretPos = alongX
    ? Math.min(Math.max(x - left, 14), Math.max(width - 14, 14))
    : Math.min(Math.max(y - top, 14), Math.max(height - 14, 14))
  caret.style.left = alongX ? `${caretPos}px` : side === 'right' ? '0' : ''
  caret.style.right = side === 'left' ? '0' : ''
  caret.style.top = alongX ? '0' : `${caretPos}px`
  caret.style.bottom = side === 'above' ? '0' : ''
  if (side === 'above') caret.style.top = ''
  const shift = side === 'below' ? 'translate(-50%, -50%)' : side === 'above' ? 'translate(-50%, 50%)' : side === 'right' ? 'translate(-50%, -50%)' : 'translate(50%, -50%)'
  caret.style.transform = `${shift} rotate(45deg)`
  caret.style.borderTopWidth = side === 'below' || side === 'left' ? '1px' : '0'
  caret.style.borderLeftWidth = side === 'below' || side === 'right' ? '1px' : '0'
  caret.style.borderRightWidth = side === 'above' || side === 'left' ? '1px' : '0'
  caret.style.borderBottomWidth = side === 'above' || side === 'right' ? '1px' : '0'
}

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
  const tipRef = useRef<HTMLSpanElement>(null)
  const caretRef = useRef<HTMLSpanElement>(null)
  const pointRef = useRef<{x: number; y: number} | null>(null)
  const [overflow, setOverflow] = useState(false)
  const [open, setOpen] = useState(false)

  useLayoutEffect(() => {
    const el = boxRef.current?.firstElementChild
    if (!(el instanceof HTMLElement)) return
    const measure = () => setOverflow(isClamped(el))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [text, className, href])

  useLayoutEffect(() => {
    const tip = tipRef.current
    const caret = caretRef.current
    const point = pointRef.current
    if (!open || !tip || !caret || !point) return
    placeBubble(tip, caret, point.x, point.y)
  }, [open, text])

  useEffect(() => {
    if (!open) return
    const hide = () => setOpen(false)
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [open])

  const track = (x: number, y: number) => {
    if (!overflow) return
    pointRef.current = {x, y}
    const tip = tipRef.current
    const caret = caretRef.current
    if (!open || !tip || !caret) {
      setOpen(true)
      return
    }
    placeBubble(tip, caret, x, y)
  }
  const followMouse = (event: ReactMouseEvent) => track(event.clientX, event.clientY)
  const followFocus = () => {
    const el = boxRef.current?.getBoundingClientRect()
    if (!el) return
    track(el.left + Math.min(el.width / 2, 48), el.bottom)
  }
  const hide = () => setOpen(false)

  const clamped = `min-w-0 line-clamp-1 break-words ${className}`
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
      onMouseEnter={followMouse}
      onMouseMove={followMouse}
      onMouseLeave={hide}
      onFocus={followFocus}
      onBlur={hide}
    >
      {body}
      {open ? (
        <span
          ref={tipRef}
          role="tooltip"
          className="pointer-events-none fixed z-30 w-max rounded-2xl border border-line bg-panel px-3 py-2 text-left text-sm font-normal leading-snug break-words text-ink shadow-card"
        >
          <span
            ref={caretRef}
            aria-hidden
            className="absolute size-2.5 border-line bg-panel"
          />
          {text}
        </span>
      ) : null}
    </div>
  )
}
