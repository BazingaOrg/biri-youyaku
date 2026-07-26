import {useState} from 'react'
import {Boxes} from 'lucide-react'
import {ApiError, getLatestDistillRun, startDistill, type DistillRun} from '../../lib/api'
import {ConfirmDialog} from '../../components/ConfirmDialog'
import {useToast} from '../../components/ToastProvider'

function getVideoLimit(value: string): number | null {
  const limit = Number(value)
  return Number.isInteger(limit) && limit >= 1 && limit <= 200 ? limit : null
}

/** 头部「蒸馏语料」按钮 + 确认层：说明耗时预期 + 可改视频范围，确认后 POST 启动。 */
export function DistillButton({mid, onStarted}: {mid: number; onStarted: (run: DistillRun) => void}) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [videoLimit, setVideoLimit] = useState('50')
  const [starting, setStarting] = useState(false)
  const limit = getVideoLimit(videoLimit)
  const videoLimitError = limit == null ? '请输入 1 到 200 之间的整数。' : null

  const start = async () => {
    if (limit == null) {
      toast.error('视频范围无效', '请输入 1 到 200 之间的整数。')
      return
    }
    setStarting(true)
    try {
      const res = await startDistill(mid, limit)
      onStarted(res.run)
      setOpen(false)
      toast.success('已开始蒸馏语料')
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // 已有进行中的 run（比如另一个标签页刚启动）：拉一次最新状态直接展示面板。
        try {
          const latest = await getLatestDistillRun(mid)
          if (latest.run) onStarted(latest.run)
        } catch {
          // 忽略；用户可以刷新页面重试
        }
        setOpen(false)
        toast.error('已有进行中的蒸馏任务', '已为你展示进度')
      } else {
        toast.error('启动蒸馏失败', err instanceof Error ? err.message : '请稍后再试')
      }
    } finally {
      setStarting(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-10 w-fit shrink-0 items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-ink transition-[transform,background-color,color] hover:bg-line/70 active:scale-95"
      >
        <Boxes size={15} />
        蒸馏语料
      </button>
      <ConfirmDialog
        open={open}
        title="蒸馏该 UP 的语料"
        description={
          <div className="grid gap-3">
            <p>
              会抓取该 UP 的历史动态，并为尚未转写的投稿补齐转写。ASR 在本地跑，视频数量多时可能
              耗时很久（几小时到几天），可以随时取消，重进页面也能看到进度。
            </p>
            <label className="grid gap-1 text-left">
              <span className="text-xs text-muted">视频范围（默认 50；数量越大越耗时，建议不超过 200）</span>
              <input
                type="number"
                min={1}
                max={200}
                value={videoLimit}
                onChange={(e) => setVideoLimit(e.target.value)}
                aria-invalid={Boolean(videoLimitError)}
                aria-describedby={videoLimitError ? 'video-limit-error' : undefined}
                className="min-h-10 w-full rounded-xl bg-lift px-3 text-sm text-ink outline-none focus:ring-2 focus:ring-brand/30"
              />
              {videoLimitError && (
                <span id="video-limit-error" className="text-xs text-danger">
                  {videoLimitError}
                </span>
              )}
            </label>
          </div>
        }
        confirmLabel="开始蒸馏"
        loading={starting}
        confirmDisabled={Boolean(videoLimitError)}
        onConfirm={() => void start()}
        onCancel={() => setOpen(false)}
      />
    </>
  )
}
