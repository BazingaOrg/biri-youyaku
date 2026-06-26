import {useState} from 'react'
import type {MouseEvent} from 'react'
import {ChevronRight, Users} from 'lucide-react'
import {Link, useLocation} from 'wouter'
import {resolveUp, type Job} from '../lib/api'
import {Spinner} from './Spinner'
import {useToast} from './ToastProvider'

type AuthorJob = Pick<Job, 'mid' | 'author' | 'url'>

/**
 * 「查看该 UP 全部投稿」入口。
 *
 * - 有 job.mid（新任务）→ 直接 Link 跳 /up/:mid，可中键新开。
 * - 没有 mid（老任务，建任务时还没有 mid 列）→ 点击时用 job.url 现场解析出 mid 再跳，
 *   所以历史里的任何作者都能打开，不需要批量回填。
 */
export function AuthorLink({job, variant = 'inline'}: {job: AuthorJob; variant?: 'inline' | 'chip'}) {
  const [, navigate] = useLocation()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const name = job.author || '未知 UP'

  const resolveAndGo = async (event: MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
    if (busy || !job.url) {
      if (!job.url) toast.error('无法定位该 UP', '这条任务缺少视频链接')
      return
    }
    setBusy(true)
    try {
      const {mid} = await resolveUp(job.url)
      navigate(`/up/${mid}`)
    } catch (err) {
      toast.error('打开投稿列表失败', err instanceof Error ? err.message : '请稍后再试')
    } finally {
      setBusy(false)
    }
  }

  const chip = variant === 'chip'
  // min-w-0：让内部名字 span 的 truncate 在窄容器里能真正生效，不把后面的时长挤出去。
  const className = chip
    ? 'inline-flex w-fit min-w-0 max-w-full items-center gap-1 rounded-full bg-panel px-2.5 py-1 text-xs font-medium text-muted transition-[background-color,color] hover:bg-brandSoft hover:text-brand active:scale-95'
    : 'inline-flex min-w-0 max-w-full items-center gap-0.5 text-xs text-muted underline-offset-2 transition-colors hover:text-brand hover:underline'

  const inner = (
    <>
      <Users size={chip ? 13 : 11} className="shrink-0" />
      <span className="truncate">{name}</span>
      {chip ? <span className="shrink-0 text-[11px] opacity-80">投稿</span> : null}
      {busy ? <Spinner size={12} className="shrink-0" /> : <ChevronRight size={chip ? 13 : 11} className="shrink-0" />}
    </>
  )

  // 有 mid 用真锚点（语义更好、可新开标签）；否则用按钮现场解析。
  if (job.mid) {
    return (
      <Link
        href={`/up/${job.mid}`}
        className={className}
        title="查看该 UP 的全部投稿"
        onClick={(e) => e.stopPropagation()}
      >
        {inner}
      </Link>
    )
  }
  return (
    <button type="button" onClick={resolveAndGo} disabled={busy} className={className} title="查看该 UP 的全部投稿">
      {inner}
    </button>
  )
}
