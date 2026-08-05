import {UpList} from './up/UpList'
import {BackButton} from '../components/BackButton'

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
