import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Link} from 'wouter'
import {listLibrary, listLibraryTrash, type LibraryListItem} from '../lib/api'
import {formatDuration, formatSavedDay} from '../lib/format'
import {Chip} from '../components/Chip'
import {OmniBar} from '../components/OmniBar'
import {Button} from '../components/Button'
import {RabbitScene} from '../components/Rabbit'
import {Skeleton} from '../components/Skeleton'
import {TaskStrips} from '../components/TaskStrips'
import {useOmniComposer} from '../hooks/useOmniComposer'
import {useTaskAlerts} from '../hooks/useTaskAlerts'
import {useUrlState} from '../hooks/useUrlState'
import {libraryItemHref} from '../lib/docNav'
import {readViewState, saveViewState} from '../lib/sessionRestore'

const PAGE_SIZE = 40

function groupLabel(savedAt?: number | null) {
  if (savedAt == null) return '更早'
  if (Date.now() - savedAt < 7 * 86_400_000) return '本周'
  return '更早'
}

export function LibraryPage() {
  const {get, setParams, pathname, search, navigate} = useUrlState()
  const up = get('up')
  const tag = get('tag')
  const paste = get('paste')
  const omni = useOmniComposer(paste)
  const {running, failed} = useTaskAlerts()
  const [items, setItems] = useState<LibraryListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<'initial' | 'partial' | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [trashCount, setTrashCount] = useState(0)
  const [retryNonce, setRetryNonce] = useState(0)
  const loadedPagesRef = useRef(1)
  const nextCursorRef = useRef<string | null>(null)
  const restore = useRef(readViewState(pathname, search))
  const restoredScroll = useRef(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setError(null)
    void (async () => {
      try {
        const restoringPages = restore.current?.loadedPages ?? 1
        let page = await listLibrary({limit: PAGE_SIZE, up: up || undefined, tag: tag || undefined}, {signal: controller.signal})
        let collected = page.items
        let cursor = page.next_cursor ?? null
        let pages = 1
        while (cursor && pages < restoringPages) {
          page = await listLibrary({limit: PAGE_SIZE, cursor, up: up || undefined, tag: tag || undefined}, {signal: controller.signal})
          const known = new Set(collected.map((item) => item.id))
          collected = [...collected, ...page.items.filter((item) => !known.has(item.id))]
          cursor = page.next_cursor ?? null
          pages += 1
        }
        if (!active) return
        setItems(collected)
        loadedPagesRef.current = pages
        nextCursorRef.current = cursor
        setNextCursor(cursor)
      } catch {
        if (!active || controller.signal.aborted) return
        setItems([])
        setError('initial')
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
      controller.abort()
    }
  }, [tag, up, retryNonce])

  useEffect(() => {
    let cancelled = false
    void listLibraryTrash()
      .then((res) => {
        if (!cancelled) setTrashCount(res.items.length)
      })
      .catch(() => {
        if (!cancelled) setTrashCount(0)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const loadMore = useCallback(async () => {
    const cursor = nextCursorRef.current
    if (!cursor || loading || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await listLibrary({limit: PAGE_SIZE, cursor, up: up || undefined, tag: tag || undefined})
      setItems((current) => {
        const known = new Set(current.map((item) => item.id))
        return [...current, ...page.items.filter((item) => !known.has(item.id))]
      })
      loadedPagesRef.current += 1
      nextCursorRef.current = page.next_cursor ?? null
      setNextCursor(nextCursorRef.current)
    } catch {
      setError('partial')
    } finally {
      setLoadingMore(false)
    }
  }, [loading, loadingMore, tag, up])

  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !nextCursor) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) void loadMore()
    }, {rootMargin: '400px'})
    observer.observe(node)
    return () => observer.disconnect()
  }, [loadMore, nextCursor])

  useEffect(() => {
    if (loading || restoredScroll.current) return
    restoredScroll.current = true
    const snap = restore.current
    if (snap) window.requestAnimationFrame(() => window.scrollTo({top: snap.scrollY}))
  }, [items, loading])

  useEffect(() => {
    return () => saveViewState(pathname, search, {scrollY: window.scrollY, loadedPages: loadedPagesRef.current})
  }, [pathname, search])

  const groups = useMemo(() => {
    const map = new Map<string, LibraryListItem[]>()
    for (const item of items) {
      const key = groupLabel(item.saved_at)
      map.set(key, [...(map.get(key) ?? []), item])
    }
    return [...map.entries()]
  }, [items])

  const filtered = Boolean(up || tag)
  const upName = items.find((item) => item.mid != null && String(item.mid) === up)?.author
  const ctx: Record<string, string> = up ? {from: 'up', up} : tag ? {from: 'tag', tag} : {from: 'library'}

  return (
    <div className="mx-auto w-full max-w-5xl">
      <OmniBar
        value={omni.value}
        onChange={omni.setValue}
        onSubmit={() => void omni.submit()}
        action={omni.action}
        busy={omni.busy}
        onGenerate={() => void omni.generate()}
        onRead={(id) => navigate(`/doc/${id}`)}
        onRestore={(id) => void omni.restore(id)}
      />
      {!filtered ? <TaskStrips running={running} failed={failed} /> : null}
      <div className="mt-7 flex flex-wrap items-center gap-2">
        <p className="mr-auto text-[13px] text-muted">
          {filtered ? '' : '全部 · '}
          {loading ? '…' : `${items.length} 篇笔记`}
        </p>
        {up ? (
          <Chip href="/" onRemove={() => setParams({up: null})}>
            UP 主：{upName || up}
          </Chip>
        ) : null}
        {tag ? (
          <Chip href="/" onRemove={() => setParams({tag: null})}>
            #{tag}
          </Chip>
        ) : null}
      </div>
      {up ? (
        <p className="mt-1 text-sm text-muted">
          只显示已保存的笔记。
          {/^\d+$/.test(up) ? (
            <Link href={`/up/${up}`} className="ml-1 text-brand">
              浏览 TA 的全部投稿 →
            </Link>
          ) : null}
        </p>
      ) : null}
      <div className="mt-3">
        {loading ? <Skeleton count={6} /> : null}
        {!loading && error === 'initial' ? (
          <RabbitScene mood="error" title="加载失败">
            <p className="text-sm text-muted">请检查网络后重试</p>
            <Button variant="secondary" onClick={() => setRetryNonce((nonce) => nonce + 1)}>
              重试
            </Button>
          </RabbitScene>
        ) : null}
        {!loading && error !== 'initial' && items.length === 0 ? (
          <RabbitScene mood={filtered ? 'search' : 'wave'} title={filtered ? '没有匹配的笔记' : '还没有笔记'}>
            <p className="text-sm text-muted">
              {filtered ? '试试去掉筛选条件。' : '粘贴一条 B 站链接，生成第一篇能回看的笔记。'}
            </p>
            {filtered ? (
              <Button variant="secondary" onClick={() => setParams({up: null, tag: null})}>
                查看全部笔记
              </Button>
            ) : null}
          </RabbitScene>
        ) : null}
        {!loading && error === 'partial' ? (
          <p role="alert" className="mb-3 text-center text-sm text-muted">
            部分记录加载失败，请稍后重试。
          </p>
        ) : null}
        {!loading && items.length > 0
          ? groups.map(([label, rows]) => (
              <section key={label}>
                {!filtered ? <h2 className="mt-7 mb-1 text-xs font-semibold tracking-[0.06em] text-muted/80">{label}</h2> : null}
                <ul>
                  {rows.map((item) => (
                    <LibraryRow key={item.id} item={item} ctx={ctx} />
                  ))}
                </ul>
              </section>
            ))
          : null}
        {nextCursor ? (
          <div className="grid justify-items-center gap-2 pt-4">
            <Button variant="ghost" onClick={() => void loadMore()} disabled={loadingMore}>
              {loadingMore ? '正在加载…' : '查看更早记录'}
            </Button>
            <div ref={sentinelRef} aria-hidden className="h-3" />
          </div>
        ) : null}
        {!filtered && trashCount > 0 ? (
          <Link href="/trash" className="mt-6 inline-flex text-[13px] text-muted hover:text-brand">
            最近删除 · {trashCount} 篇
          </Link>
        ) : null}
      </div>
    </div>
  )
}

function LibraryRow({
  item,
  ctx,
}: {
  item: LibraryListItem
  ctx: Record<string, string>
}) {
  const href = libraryItemHref(item, ctx)
  const missing = item.legacy_reason === 'summary_file_missing'
  return (
    <li className="grid grid-cols-1 gap-1 border-b border-line py-3.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:gap-x-4">
      <div className="grid min-w-0 gap-1">
        <Link href={href} className="line-clamp-2 text-base font-semibold leading-snug break-words hover:text-brand">
          {item.title}
        </Link>
        {item.tldr ? <p className="line-clamp-1 text-sm text-muted">{item.tldr}</p> : null}
        <p className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px] text-muted">
          {item.mid ? (
            <Link href={`/?up=${item.mid}`} className="text-ink/80 hover:text-brand">
              {item.author || '未知 UP'}
            </Link>
          ) : (
            <span>{item.author || '未知 UP'}</span>
          )}
          <span>{formatDuration(item.duration ?? undefined)}</span>
          {item.tags.map((tag) => (
            <Link key={tag} href={`/?tag=${encodeURIComponent(tag)}`} className="hover:text-brand">
              #{tag}
            </Link>
          ))}
          {item.legacy || missing ? (
            <span className="rounded-md bg-lift px-1.5 py-0.5 text-[11px] text-muted">
              {missing ? '笔记文件已丢失，可重新生成' : '旧版 · 仅支持标题搜索'}
            </span>
          ) : null}
        </p>
      </div>
      <span className="hidden text-right text-xs tabular-nums text-muted/80 sm:block sm:pt-1">
        {formatSavedDay(item.saved_at)}
      </span>
    </li>
  )
}
