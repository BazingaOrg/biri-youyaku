import {useCallback, useEffect, useState} from 'react'
import {Link} from 'wouter'
import {listLibraryTrash, purgeDocument, restoreDocument, type TrashItem} from '../lib/api'
import {formatDate} from '../lib/format'
import {BackButton} from '../components/BackButton'
import {Button} from '../components/Button'
import {ConfirmDialog} from '../components/ConfirmDialog'
import {Skeleton} from '../components/Skeleton'
import {useToast} from '../components/ToastProvider'

export function TrashPage() {
  const toast = useToast()
  const [items, setItems] = useState<TrashItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [purgeItem, setPurgeItem] = useState<TrashItem | null>(null)
  const [purgeInput, setPurgeInput] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await listLibraryTrash()
      setItems(response.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const restore = async (item: TrashItem) => {
    setBusyId(item.document_id)
    try {
      await restoreDocument(item.document_id)
      setItems((current) => current.filter((row) => row.document_id !== item.document_id))
      toast.success('已恢复笔记')
    } catch (err) {
      toast.error('恢复失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setBusyId(null)
    }
  }

  const purge = async () => {
    if (!purgeItem) return
    setBusyId(purgeItem.document_id)
    try {
      await purgeDocument(purgeItem.document_id, purgeInput.trim())
      setItems((current) => current.filter((row) => row.document_id !== purgeItem.document_id))
      setPurgeItem(null)
      setPurgeInput('')
      toast.success('已永久删除')
    } catch (err) {
      toast.error('删除失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl">
      <BackButton href="/" label="全部笔记" />
      <h1 className="mt-3 text-2xl font-semibold tracking-[-0.012em]">最近删除</h1>
      <p className="mt-1 text-sm text-muted">30 天内可以恢复。到期后会自动清除。</p>
      <div className="mt-6">
        {loading ? <Skeleton count={4} /> : null}
        {error ? (
          <div className="grid justify-items-center gap-3 py-12 text-center">
            <p className="text-sm text-muted">{error}</p>
            <Button variant="secondary" onClick={() => void load()}>
              重试
            </Button>
          </div>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted">最近删除是空的</p>
        ) : null}
        {!loading && items.length > 0 ? (
          <ul>
            {items.map((item) => {
              const soon = item.days_left <= 3
              return (
                <li
                  key={item.document_id}
                  className="grid grid-cols-1 gap-2 border-b border-line py-3.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                >
                  <div className="min-w-0">
                    <Link href={`/doc/${item.document_id}?from=trash`} className="line-clamp-2 font-semibold hover:text-brand">
                      {item.title || '未命名'}
                    </Link>
                    <p className="mt-0.5 flex flex-wrap gap-x-2.5 text-[13px] text-muted">
                      <span>{item.author || '未知 UP'}</span>
                      {item.deleted_at ? <span>{formatDate(item.deleted_at)} 移除</span> : null}
                      <span className={soon ? 'font-medium text-warning' : ''}>还剩 {item.days_left} 天</span>
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={busyId === item.document_id}
                      onClick={() => void restore(item)}
                    >
                      恢复
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busyId === item.document_id}
                      onClick={() => {
                        setPurgeItem(item)
                        setPurgeInput('')
                      }}
                    >
                      永久删除
                    </Button>
                  </div>
                </li>
              )
            })}
          </ul>
        ) : null}
      </div>
      <ConfirmDialog
        open={purgeItem != null}
        title="永久删除这篇笔记？"
        description={
          <div className="grid gap-3">
            <p>笔记、字幕和历史版本都会删除，无法恢复。任务记录和 B 站视频不受影响。</p>
            <label className="grid gap-1 text-left text-[13px]">
              <span>
                输入 BV 号 <b className="font-mono text-ink">{purgeItem?.bvid}</b> 确认
              </span>
              <input
                value={purgeInput}
                onChange={(event) => setPurgeInput(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                className="min-h-[42px] rounded-[10px] border border-line bg-canvas px-3 font-mono text-sm outline-none focus:border-danger"
              />
            </label>
          </div>
        }
        confirmLabel="永久删除"
        danger
        loading={busyId === purgeItem?.document_id}
        confirmDisabled={!purgeItem?.bvid || purgeInput.trim() !== purgeItem.bvid}
        onConfirm={() => void purge()}
        onCancel={() => {
          setPurgeItem(null)
          setPurgeInput('')
        }}
      />
    </div>
  )
}
