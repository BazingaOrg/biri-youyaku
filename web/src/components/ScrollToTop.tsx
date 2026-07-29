import {useEffect, useState} from 'react'
import {ArrowUp} from 'lucide-react'
import {smoothScrollTo} from '../lib/scroll'

/** 「回到顶部」；由 AppShell 右下工具区挂载，滚动后出现在主题按钮上方。 */
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
      className="grid h-11 w-11 place-items-center rounded-full border border-line bg-panel/80 text-muted shadow-card backdrop-blur transition hover:text-brand active:scale-95"
    >
      <ArrowUp size={20} />
    </button>
  )
}
