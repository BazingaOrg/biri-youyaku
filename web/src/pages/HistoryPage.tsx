import {useCallback, useEffect, useMemo, useState} from 'react'
import {Search, Trash2} from 'lucide-react'
import type {Job, JobStatus} from '../lib/api'
import {deleteAllJobs, deleteJob, listJobs} from '../lib/api'
import {HistoryItem} from '../components/HistoryItem'
import {ConfirmDialog} from '../components/ConfirmDialog'
import {useToast} from '../components/ToastProvider'
import {useShortcuts} from '../hooks/useShortcuts'

interface HistoryPageProps {
  onOpen: (jobId: string) => void
}

const statusFilters: Array<{label: string; value: 'all' | JobStatus[]}> = [
  {label: '全部', value: 'all'},
  {label: '进行中', value: ['PENDING', 'FETCHING_META', 'DOWNLOADING_AUDIO', 'TRANSCRIBING', 'SUMMARIZING', 'EMAILING']},
  {label: '待确认', value: ['TRANSCRIPT_READY']},
  {label: '已完成', value: ['COMPLETED']},
  {label: '失败', value: ['FAILED', 'CANCELED']},
]

function groupLabel(createdAt: number) {
  const date = new Date(createdAt)
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000
  const startOfWeek = startOfToday - 6 * 24 * 60 * 60 * 1000
  if (date.getTime() >= startOfToday) return '今天'
  if (date.getTime() >= startOfYesterday) return '昨天'
  if (date.getTime() >= startOfWeek) return '本周'
  return '更早'
}

/** Deduplicate jobs by bvid+cid: keep the most recent as the "main" card and
 *  return earlier runs as `versions`.  Jobs without bvid (e.g. still fetching
 *  meta) are always shown as standalone cards. */
function deduplicateJobs(jobs: Job[]): Array<{main: Job; versions: Job[]}> {
  const grouped = new Map<string, Job[]>()
  const standalone: Job[] = []

  for (const job of jobs) {
    if (job.bvid) {
      const key = `${job.bvid}:${job.cid ?? ''}`
      const group = grouped.get(key)
      if (group) {
        group.push(job)
      } else {
        grouped.set(key, [job])
      }
    } else {
      standalone.push(job)
    }
  }

  const result: Array<{main: Job; versions: Job[]}> = []
  for (const group of grouped.values()) {
    // jobs are already sorted newest-first from the API
    result.push({main: group[0], versions: group.slice(1)})
  }
  for (const job of standalone) {
    result.push({main: job, versions: []})
  }

  // Re-sort the deduplicated entries by their main job's created_at (desc)
  result.sort((a, b) => b.main.created_at - a.main.created_at)
  return result
}

export function HistoryPage({onOpen}: HistoryPageProps) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<{type: 'one' | 'all'; job?: Job} | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [query, setQuery] = useState('')
  const [filterIndex, setFilterIndex] = useState(0)
  const [nextCursor, setNextCursor] = useState<number | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const toast = useToast()
  useShortcuts({
    onFocusSearch: () => document.getElementById('history-search')?.focus(),
  })

  const reload = useCallback(() => {
    listJobs()
      .then((response) => {
        setJobs(response.jobs)
        setNextCursor(response.next_cursor ?? null)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : '加载历史失败'))
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const loadMore = async () => {
    if (nextCursor == null || loadingMore) {
      return
    }
    setLoadingMore(true)
    try {
      const response = await listJobs({cursor: nextCursor})
      setJobs((current) => [...current, ...response.jobs])
      setNextCursor(response.next_cursor ?? null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载更多历史失败')
    } finally {
      setLoadingMore(false)
    }
  }

  const filteredGroups = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    const filter = statusFilters[filterIndex].value

    // Filter individual jobs first
    const filtered = jobs.filter((job) => {
      const matchesQuery = !normalizedQuery || [job.title, job.author, job.bvid, job.url].some((value) => (value || '').toLowerCase().includes(normalizedQuery))
      const matchesStatus = filter === 'all' || filter.includes(job.status)
      return matchesQuery && matchesStatus
    })

    // Deduplicate by BV+CID
    const deduped = deduplicateJobs(filtered)

    // Group deduplicated entries by date (based on main job's created_at)
    return deduped.reduce<Array<{label: string; items: typeof deduped}>>(
      (groups, item) => {
        const label = groupLabel(item.main.created_at)
        const group = groups.find((g) => g.label === label)
        if (group) {
          group.items.push(item)
        } else {
          groups.push({label, items: [item]})
        }
        return groups
      },
      [],
    )
  }, [filterIndex, jobs, query])

  const handleDelete = async () => {
    if (!confirm) {
      return
    }
    setDeleting(true)
    try {
      if (confirm.type === 'all') {
        const response = await deleteAllJobs()
        toast.success('历史已清理', `已删除 ${response.deleted_count} 个任务，保留 ${response.skipped_count} 个进行中任务。`, {autoClose: true})
      } else if (confirm.job) {
        await deleteJob(confirm.job.id)
        toast.success('任务已删除', confirm.job.title || confirm.job.url, {autoClose: true})
      }
      setConfirm(null)
      reload()
    } catch (err) {
      const message = err instanceof Error ? err.message : '删除任务失败'
      setError(message)
      toast.error('删除失败', message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="grid gap-4">
      <div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold">历史任务</h1>
            <p className="mt-2 text-sm text-muted">按创建时间倒序排列，点击任一任务查看总结和状态。</p>
          </div>
          <button
            type="button"
            onClick={() => setConfirm({type: 'all'})}
            disabled={jobs.length === 0}
            className="inline-flex min-h-10 items-center gap-2 rounded-xl px-4 text-sm font-semibold text-danger transition hover:bg-red-50 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Trash2 size={16} />
            清除全部
          </button>
        </div>
      </div>
      <section className="grid gap-3 rounded-3xl bg-panel p-3 shadow-card">
        <label className="flex min-h-11 items-center gap-2 rounded-2xl bg-lift px-3">
          <Search size={17} className="text-muted" />
          <input id="history-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、UP 主或 BV 号" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted/60" />
        </label>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {statusFilters.map((filter, index) => (
            <button key={filter.label} type="button" onClick={() => setFilterIndex(index)} className={`min-h-10 shrink-0 rounded-xl px-3 text-sm font-medium transition active:scale-95 ${filterIndex === index ? 'bg-brand text-white' : 'bg-lift text-muted hover:text-ink'}`}>
              {filter.label}
            </button>
          ))}
        </div>
      </section>
      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-danger">{error}</p>}
      <div className="grid gap-3">
        {filteredGroups.map((group) => (
          <section key={group.label} className="grid gap-2">
            <h2 className="px-1 text-sm font-semibold text-muted">{group.label}</h2>
            {group.items.map(({main, versions}) => (
              <HistoryItem
                key={main.id}
                job={main}
                versions={versions}
                onOpen={onOpen}
                onDelete={() => setConfirm({type: 'one', job: main})}
                onDeleteVersion={(id) => {
                  const versionJob = versions.find((v) => v.id === id)
                  setConfirm({type: 'one', job: versionJob ?? main})
                }}
              />
            ))}
          </section>
        ))}
        {filteredGroups.length === 0 && !error && (
          <div className="rounded-3xl bg-panel p-8 text-center text-muted shadow-card">暂无匹配任务</div>
        )}
        {nextCursor != null && (
          <button type="button" onClick={loadMore} disabled={loadingMore} className="min-h-11 rounded-2xl bg-lift px-4 text-sm font-medium text-muted transition hover:bg-line/70 active:scale-95 disabled:opacity-50">
            {loadingMore ? '加载中...' : '加载更多'}
          </button>
        )}
      </div>
      <ConfirmDialog
        open={confirm != null}
        title={confirm?.type === 'all' ? '清除全部历史？' : '删除这个任务？'}
        description={confirm?.type === 'all'
          ? '将删除所有已完成、失败、已取消或等待确认的任务；正在运行的任务会被保留。此操作不可撤销。'
          : `将删除「${confirm?.job?.title || confirm?.job?.url || ''}」及其本地总结/音频记录。此操作不可撤销。`}
        confirmLabel={confirm?.type === 'all' ? '清除全部' : '删除任务'}
        tone="danger"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirm(null)}
      />
    </div>
  )
}
