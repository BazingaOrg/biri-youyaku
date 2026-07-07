import {useCallback, useState} from 'react'
import ReactMarkdown from 'react-markdown'
import {AlertTriangle, Boxes, ChevronDown, ChevronUp, FolderOpen, RotateCw, X} from 'lucide-react'
import {
  cancelDistill,
  getDistillCorpus,
  startDistill,
  type DistillCounters,
  type DistillRun,
  type DistillRunStatus,
  type DistillStatusPayload,
} from '../lib/api'
import {useDistillStream} from '../hooks/useDistillStream'
import {useToast} from './ToastProvider'
import {PROSE} from '../pages/workspace/SummaryTabs'

const STAGE_LABELS: Record<DistillRunStatus, string> = {
  PENDING: '排队中',
  FETCHING_DYNAMICS: '抓取动态',
  PREPARING_TRANSCRIPTS: '准备转写',
  EXTRACTING: '提取观点',
  ASSEMBLING: '组装中',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
}

const TERMINAL_STATUSES: DistillRunStatus[] = ['COMPLETED', 'FAILED', 'CANCELLED']

interface DistillPanelProps {
  mid: number
  run: DistillRun
  /** 重新开始会创建一个新 run（新 id）；父组件应以 `key={run.id}` 挂载本组件，
   * 这样切换到新 run 时内部状态（语料预览展开态等）会自然重置。 */
  onRunChange: (run: DistillRun) => void
}

/** UpPage 头部的蒸馏进度面板：订阅 SSE、展示阶段/计数/取消，终态时展示语料入口或重试。 */
export function DistillPanel({mid, run: initialRun, onRunChange}: DistillPanelProps) {
  const toast = useToast()
  const [run, setRun] = useState(initialRun)
  const [cancelling, setCancelling] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [corpusOpen, setCorpusOpen] = useState(false)
  const [corpusText, setCorpusText] = useState<string | null>(null)
  const [corpusLoading, setCorpusLoading] = useState(false)
  const [corpusError, setCorpusError] = useState<string | null>(null)

  const terminal = TERMINAL_STATUSES.includes(run.status)

  const onPatch = useCallback((payload: DistillStatusPayload) => {
    setRun((prev) => {
      // 订阅后的第一条消息是完整快照（GET /distill/{run_id} 同款序列化），计数字段
      // 嵌在 `counters` 里；之后 orchestrator 推的是增量事件，计数字段摊平在顶层。
      // 两种形状都可能出现，逐个字段做「有则覆盖，没有保留上一次」的合并。
      const snapshotCounters = payload.counters as Partial<DistillCounters> | undefined
      return {
        ...prev,
        status: payload.status,
        dynamics_status: payload.dynamics_status ?? prev.dynamics_status,
        error: payload.error ?? prev.error,
        counters: {
          ...prev.counters,
          dynamics_count: payload.dynamics_count ?? snapshotCounters?.dynamics_count ?? prev.counters.dynamics_count,
          videos_total: payload.videos_total ?? snapshotCounters?.videos_total ?? prev.counters.videos_total,
          videos_transcribed:
            payload.videos_transcribed ?? snapshotCounters?.videos_transcribed ?? prev.counters.videos_transcribed,
          videos_extracted:
            payload.videos_extracted ?? snapshotCounters?.videos_extracted ?? prev.counters.videos_extracted,
          videos_failed: snapshotCounters?.videos_failed ?? prev.counters.videos_failed,
          failed_bvids: snapshotCounters?.failed_bvids ?? prev.counters.failed_bvids,
        },
      }
    })
  }, [])

  useDistillStream(terminal ? null : run.id, onPatch)

  const loadCorpus = useCallback(async () => {
    if (corpusText !== null) {
      setCorpusOpen((open) => !open)
      return
    }
    setCorpusLoading(true)
    setCorpusError(null)
    try {
      const res = await getDistillCorpus(run.id)
      setCorpusText(res.corpus)
      setCorpusOpen(true)
    } catch (err) {
      setCorpusError(err instanceof Error ? err.message : '加载语料失败，请稍后再试')
    } finally {
      setCorpusLoading(false)
    }
  }, [run.id, corpusText])

  const cancel = async () => {
    setCancelling(true)
    try {
      await cancelDistill(run.id)
      toast.success('已提交取消，稍后会停止')
    } catch (err) {
      toast.error('取消失败', err instanceof Error ? err.message : '请稍后再试')
    } finally {
      setCancelling(false)
    }
  }

  const restart = async () => {
    setRestarting(true)
    try {
      const res = await startDistill(mid, run.video_limit)
      onRunChange(res.run)
      toast.success('已重新开始蒸馏')
    } catch (err) {
      toast.error('重新开始失败', err instanceof Error ? err.message : '请稍后再试')
    } finally {
      setRestarting(false)
    }
  }

  const counters = run.counters
  const progress =
    run.status === 'PREPARING_TRANSCRIPTS' && counters.videos_total > 0
      ? {done: counters.videos_transcribed, total: counters.videos_total}
      : run.status === 'EXTRACTING' && counters.videos_total > 0
        ? {done: counters.videos_extracted, total: counters.videos_total}
        : null

  return (
    <section className="grid gap-3 rounded-2xl bg-lift/70 p-4 shadow-card sm:p-5">
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Boxes size={16} className="text-brand" />
          蒸馏语料
        </div>
        {!terminal && (
          <button
            type="button"
            onClick={() => void cancel()}
            disabled={cancelling}
            className="inline-flex min-h-8 items-center gap-1 rounded-xl bg-lift px-3 text-xs text-muted transition hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-50"
          >
            <X size={13} />
            {cancelling ? '取消中…' : '取消'}
          </button>
        )}
      </header>

      {run.status === 'FAILED' && (
        <div className="grid gap-3">
          <div className="flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span className="break-words">{run.error || '蒸馏失败，原因未知'}</span>
          </div>
          <RestartButton restarting={restarting} onClick={() => void restart()} />
        </div>
      )}

      {run.status === 'CANCELLED' && (
        <div className="grid gap-3">
          <p className="text-sm text-muted">已取消。</p>
          <RestartButton restarting={restarting} onClick={() => void restart()} />
        </div>
      )}

      {run.status !== 'FAILED' && run.status !== 'CANCELLED' && (
        <div className="grid gap-2">
          <div className="flex items-center gap-2 text-sm text-ink">
            {!terminal && <RotateCw size={14} className="animate-spin text-brand" />}
            <span>
              {STAGE_LABELS[run.status]}
              {progress && ` ${progress.done}/${progress.total}`}
            </span>
          </div>
          {progress && (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-lift">
              <div
                className="h-full rounded-full bg-brand transition-[width]"
                style={{width: `${Math.min(100, (progress.done / progress.total) * 100)}%`}}
              />
            </div>
          )}
          {run.dynamics_status === 'unavailable' && (
            <p className="flex items-center gap-1 text-xs text-warning">
              <AlertTriangle size={12} />
              动态不可用，仅使用投稿语料
            </p>
          )}
          {run.status === 'COMPLETED' && (
            <div className="grid gap-2 pt-1">
              <p className="break-all font-mono text-xs text-muted">{run.dir_path}</p>
              <button
                type="button"
                onClick={() => void loadCorpus()}
                disabled={corpusLoading}
                className="inline-flex min-h-9 w-fit items-center gap-1 rounded-xl bg-brandSoft px-3 text-xs font-medium text-brand transition hover:brightness-95 active:scale-95 disabled:opacity-50"
              >
                <FolderOpen size={14} />
                {corpusLoading ? '加载中…' : '查看语料'}
                {corpusText !== null && (corpusOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />)}
              </button>
              {corpusError && <p className="text-xs text-danger">{corpusError}</p>}
              {corpusOpen && corpusText !== null && (
                <div className={`max-h-[50vh] overflow-y-auto rounded-xl bg-panel p-3 ${PROSE}`}>
                  <ReactMarkdown>{corpusText}</ReactMarkdown>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function RestartButton({restarting, onClick}: {restarting: boolean; onClick: () => void}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={restarting}
      className="inline-flex min-h-9 w-fit items-center gap-1 rounded-xl bg-brand px-3 text-xs font-medium text-white shadow-card transition hover:brightness-105 active:scale-95 disabled:opacity-50"
    >
      <RotateCw size={13} className={restarting ? 'animate-spin' : undefined} />
      重新开始
    </button>
  )
}
