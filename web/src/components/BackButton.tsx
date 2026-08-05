import {ArrowLeft} from 'lucide-react'
import {useLocation} from 'wouter'

/** Shared back button used across History / Knowledge / Up pages. */
export function BackButton() {
  const [, navigate] = useLocation()
  const onBack = () => {
    if (window.history.length > 1) window.history.back()
    else navigate('/')
  }
  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex min-h-10 w-fit items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
    >
      <ArrowLeft size={16} />
      返回
    </button>
  )
}
