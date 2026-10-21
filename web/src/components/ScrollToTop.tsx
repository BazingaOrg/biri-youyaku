import {useEffect, useState} from 'react'
import {ArrowUp} from 'lucide-react'
import {smoothScrollTo} from '../lib/scroll'

/** 「回到顶部」；滚过一屏后出现在右下角。 */
export function ScrollToTop() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 600)
    onScroll()
    window.addEventListener('scroll', onScroll, {passive: true})
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  if (!show) return null
  return (
    <button
      type="button"
      onClick={() => smoothScrollTo({top: 0})}
      aria-label="回到顶部"
      className="grid h-9 w-9 place-items-center rounded-[10px] bg-panel text-muted hover:bg-lift hover:text-ink"
    >
      <ArrowUp size={20} />
    </button>
  )
}
