import {useLocation} from 'wouter'
import {ArrowLeft} from 'lucide-react'
import {UpList} from './up/UpList'

interface UpPageProps {
  /** /up/:mid 的 uid 字符串。入口保留在历史作者名点击，不再提供独立 /up 搜索页。 */
  mid: string
}

export function UpPage({mid}: UpPageProps) {
  const numeric = Number(mid)
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return (
      <div className="grid min-h-[40vh] place-items-center gap-3 px-4 text-center">
        <p className="text-sm text-muted">无效的 UP 主 UID</p>
        <BackButton />
      </div>
    )
  }
  return <UpList key={mid} mid={numeric} />
}

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

