import {useEffect, useState} from 'react'
import {ArrowUp} from 'lucide-react'

/** 滚动超过一屏后出现的「回到顶部」浮标。全局挂一个即可。 */
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
      onClick={() => window.scrollTo({top: 0, behavior: 'smooth'})}
      aria-label="回到顶部"
      className="fixed bottom-5 left-5 z-30 grid h-11 w-11 place-items-center rounded-full border border-line bg-panel text-muted shadow-card transition hover:text-brand"
    >
      <ArrowUp size={20} />
    </button>
  )
}
