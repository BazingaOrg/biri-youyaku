// localStorage 里只保留一条「当前正在跑的任务」指针。
// 用户提交时写入，进入 / 路由时检查；终态（COMPLETED/FAILED/CANCELED）就清掉。
// 历史任务不走这里，走列表。
const STORAGE_KEY = 'biri:active'
const STALE_MS = 24 * 60 * 60 * 1000 // 超过 24h 视为过期，直接清掉

export interface ActiveJobPointer {
  jobId: string
  url: string
  createdAt: number
}

export function readActive(): ActiveJobPointer | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ActiveJobPointer>
    if (typeof parsed.jobId !== 'string' || typeof parsed.createdAt !== 'number') {
      return null
    }
    if (Date.now() - parsed.createdAt > STALE_MS) {
      clearActive()
      return null
    }
    return {
      jobId: parsed.jobId,
      url: typeof parsed.url === 'string' ? parsed.url : '',
      createdAt: parsed.createdAt,
    }
  } catch {
    return null
  }
}

export function writeActive(pointer: Omit<ActiveJobPointer, 'createdAt'> & {createdAt?: number}) {
  try {
    const payload: ActiveJobPointer = {
      jobId: pointer.jobId,
      url: pointer.url,
      createdAt: pointer.createdAt ?? Date.now(),
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // localStorage 不可用就静默：状态恢复是 nice-to-have。
  }
}

export function clearActive(matchJobId?: string) {
  try {
    if (matchJobId) {
      const current = readActive()
      if (current && current.jobId !== matchJobId) return
    }
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

/** 在跨标签同步时监听 storage 事件。返回 unsubscribe。 */
export function subscribeActive(handler: (pointer: ActiveJobPointer | null) => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return
    handler(readActive())
  }
  window.addEventListener('storage', onStorage)
  return () => window.removeEventListener('storage', onStorage)
}
