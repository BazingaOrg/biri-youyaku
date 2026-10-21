import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Link} from 'wouter'
import {searchLibrary, type LibrarySearchGroup, type LibrarySearchResponse} from '../lib/api'
import {formatClock, formatDuration, formatSavedDay} from '../lib/format'
import {Button} from '../components/Button'
import {RabbitScene} from '../components/Rabbit'
import {OmniBar} from '../components/OmniBar'
import {Segmented} from '../components/Segmented'
import {SearchHighlight} from '../components/SearchHighlight'
import {Skeleton} from '../components/Skeleton'
import {useOmniComposer} from '../hooks/useOmniComposer'
import {useUrlState} from '../hooks/useUrlState'
import {docHref} from '../lib/docNav'
import {parseSearchScope, type SearchScope} from '../lib/urlState'
import {readViewState, saveViewState} from '../lib/sessionRestore'

export function SearchPage() {
  const {get, setParams, pathname, search, navigate} = useUrlState()
  const q = get('q')
  const scope = parseSearchScope(get('scope'))
  const omni = useOmniComposer(q)
  const [result, setResult] = useState<LibrarySearchResponse | null>(null)
  const [loading, setLoading] = useState(Boolean(q.trim()))
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)
  const loadedPagesRef = useRef(1)
  const nextCursorRef = useRef<string | null>(null)
  const generationRef = useRef(0)
  const restore = useRef(readViewState(pathname, search))
  const restoredScroll = useRef(false)

  useEffect(() => {
    const generation = ++generationRef.current
    const controller = new AbortController()
    const trimmed = q.trim()
    if (!trimmed) {
      setResult(null)
      setLoading(false)
      setNextCursor(null)
      nextCursorRef.current = null
      return () => controller.abort()
    }
    setLoading(true)
    setError(null)
    void searchLibrary({q: trimmed, scope, limit: 30}, {signal: controller.signal})
      .then((page) => {
        if (generation !== generationRef.current) return
        setResult(page)
        loadedPagesRef.current = 1
        nextCursorRef.current = page.next_cursor
        setNextCursor(page.next_cursor)
      })
      .catch((err) => {
        if (controller.signal.aborted || generation !== generationRef.current) return
        setResult(null)
        setNextCursor(null)
        nextCursorRef.current = null
        setError(err instanceof Error ? err.message : '检索失败')
      })
      .finally(() => {
        if (generation === generationRef.current) setLoading(false)
      })
    return () => controller.abort()
  }, [q, scope, retryNonce])

  const loadMore = useCallback(async () => {
    const cursor = nextCursorRef.current
    const trimmed = q.trim()
    if (!cursor || !trimmed || loading || loadingMore) return
    const generation = generationRef.current
    setLoadingMore(true)
    try {
      const page = await searchLibrary({q: trimmed, scope, cursor, limit: 30})
      if (generation !== generationRef.current) return
      setResult((current) => {
        if (!current) return page
        const known = new Set(current.groups.map((group) => group.document_id || group.job_id || group.title))
        return {
          ...current,
          partial: page.partial.length ? page.partial : current.partial,
          groups: [...current.groups, ...page.groups.filter((group) => !known.has(group.document_id || group.job_id || group.title))],
        }
      })
      loadedPagesRef.current += 1
      nextCursorRef.current = page.next_cursor
      setNextCursor(page.next_cursor)
    } catch (err) {
      if (generation !== generationRef.current) return
      setError(err instanceof Error ? err.message : '检索失败')
    } finally {
      if (generation === generationRef.current) setLoadingMore(false)
    }
  }, [loading, loadingMore, q, scope])

  useEffect(() => {
    if (loading || restoredScroll.current) return
    restoredScroll.current = true
    const snap = restore.current
    if (snap) window.requestAnimationFrame(() => window.scrollTo({top: snap.scrollY}))
  }, [loading, result])

  useEffect(() => {
    return () => saveViewState(pathname, search, {scrollY: window.scrollY, loadedPages: loadedPagesRef.current})
  }, [pathname, search])

  const pageCounts = useMemo(() => {
    const groups = result?.groups ?? []
    const notes = groups.reduce((sum, group) => sum + group.hit_counts.notes, 0)
    const subs = groups.reduce((sum, group) => sum + group.hit_counts.subs, 0)
    return {
      notes: result?.hit_counts?.notes ?? notes,
      subs: result?.hit_counts?.subs ?? subs,
    }
  }, [result])

  const partial = result?.partial ?? []
  const scopedEmptyHint = (() => {
    if (scope === 'notes') return '已在标题、UP 主、BV 号、标签和笔记中查找。'
    if (scope === 'subs') return '已在字幕中查找。'
    return '已在标题、UP 主、BV 号、标签、笔记和字幕中查找。'
  })()

  return (
    <div className="mx-auto w-full max-w-5xl">
      <OmniBar
        value={omni.value}
        onChange={omni.setValue}
        onSubmit={() => void omni.submit()}
        action={omni.action}
        busy={omni.busy}
        hint={false}
        onGenerate={() => void omni.generate()}
        onRead={(id) => navigate(`/doc/${id}`)}
        onRestore={(id) => void omni.restore(id)}
      />
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Segmented
          ariaLabel="搜索范围"
          value={scope}
          onChange={(next) => setParams({scope: next, q: q || omni.value.trim()})}
          options={[
            {value: 'all', label: '全部'},
            {value: 'notes', label: '笔记', count: result && !nextCursor ? pageCounts.notes : null},
            {value: 'subs', label: '字幕', count: result && !nextCursor ? pageCounts.subs : null},
          ]}
        />
        {result ? (
          <span className="ml-auto text-[13px] text-muted">
            {nextCursor ? `已显示 ${result.groups.length} 个视频` : `${result.groups.length} 个视频`}
          </span>
        ) : null}
      </div>
      {partial.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl bg-warning/15 px-3.5 py-2.5 text-sm">
          <span className="min-w-0 flex-1 basis-[240px]">
            {partial.includes('subs') && partial.includes('notes')
              ? '笔记和字幕索引暂时不可用，下面只包含标题等元信息。'
              : partial.includes('subs')
                ? '字幕索引暂时不可用，下面只包含标题和笔记的结果。'
                : '笔记索引暂时不可用，下面只包含标题和字幕的结果。'}
          </span>
          <Button size="sm" variant="secondary" onClick={() => setRetryNonce((nonce) => nonce + 1)}>
            重试
          </Button>
        </div>
      ) : null}
      {error && !result ? (
        <RabbitScene mood="error" title="检索失败">
          <p className="text-sm text-muted">{error}</p>
          <Button variant="secondary" onClick={() => setRetryNonce((nonce) => nonce + 1)}>
            重试
          </Button>
        </RabbitScene>
      ) : null}
      {error && result ? <p className="mt-4 text-sm text-danger">{error}</p> : null}
      {loading ? <div className="mt-4"><Skeleton count={5} /></div> : null}
      {!loading && !error && !q.trim() ? (
        <p className="py-12 text-center text-sm text-muted">输入关键词，按 Enter 搜索</p>
      ) : null}
      {!loading && !error && q.trim() && result && result.groups.length === 0 && partial.length === 0 ? (
        <RabbitScene mood="search" title={`没有找到「${q}」`}>
          <p className="text-sm leading-6 text-muted">
            {scopedEmptyHint}
            <br />
            换个更短的关键词试试；如果它是一个视频链接，直接粘贴就能生成笔记。
          </p>
          <div className="mt-4">
            <Button variant="secondary" onClick={() => navigate('/')}>
              查看全部笔记
            </Button>
          </div>
        </RabbitScene>
      ) : null}
      {!loading && result
        ? result.groups.map((group) => (
            <ResultGroup key={`${group.document_id || group.job_id}-${group.title}`} group={group} query={result.query} scope={scope} />
          ))
        : null}
      {nextCursor ? (
        <div className="py-4 text-center">
          <Button variant="secondary" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? '加载中…' : '查看更多结果'}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function ResultGroup({
  group,
  query,
  scope,
}: {
  group: LibrarySearchGroup
  query: string
  scope: SearchScope
}) {
  const [open, setOpen] = useState(false)
  const id = group.document_id || group.job_id
  const ctx = {from: 'search', q: query, scope}
  const hits = group.hits.filter((hit) => (scope === 'all' ? true : hit.kind === scope))
  const shown = open ? hits : hits.slice(0, 2)
  const rest = hits.length - shown.length
  const meta: string[] = []
  if (group.match.title) meta.push('标题')
  if (group.match.author) meta.push('UP 主')
  if (group.match.bvid) meta.push('BV 号')
  if (group.match.tags.length) meta.push('标签')
  const missing = group.legacy_reason === 'summary_file_missing'

  return (
    <article className="border-b border-line py-4">
      <div className="flex flex-wrap items-baseline gap-2">
        {id ? (
          <Link href={docHref(id, ctx)} className="min-w-0 flex-1 basis-[300px] text-base font-semibold leading-snug break-words hover:text-brand">
            <SearchHighlight text={group.title} query={query} mode="fts" />
          </Link>
        ) : (
          <p className="text-base font-semibold">
            <SearchHighlight text={group.title} query={query} mode="fts" />
          </p>
        )}
      </div>
      <p className="mt-0.5 flex flex-wrap gap-x-2.5 gap-y-1 text-[13px] text-muted">
        <span>
          <SearchHighlight text={group.author || '未知 UP'} query={query} />
        </span>
        <span>{formatDuration(group.duration ?? undefined)}</span>
        <span>{formatSavedDay(group.saved_at)}</span>
        {meta.length ? <span className="text-brand">{meta.join('、')}匹配</span> : null}
        {group.legacy || missing ? (
          <span className="rounded-md bg-lift px-1.5 py-0.5 text-[11px]">
            {missing ? '笔记文件已丢失，可重新生成' : '旧版 · 仅支持标题搜索'}
          </span>
        ) : null}
      </p>
      {shown.length > 0 ? (
        <ul className="mt-2.5 grid gap-0.5">
          {shown.map((hit, index) => {
            const tab = hit.kind === 'notes' ? 'notes' : 'subs'
            const at =
              hit.kind === 'subs'
                ? hit.start_sec != null
                  ? String(Math.floor(hit.start_sec))
                  : String(index)
                : hit.chunk_ord != null
                  ? String(hit.chunk_ord)
                  : String(index)
            const href = id ? docHref(id, {...ctx, tab, at}) : undefined
            const body = (
              <>
                <span className="text-xs text-muted">
                  <b className="font-medium text-ink/70">{hit.kind === 'notes' ? '笔记' : '字幕'}</b>{' '}
                  {hit.kind === 'subs' && hit.start_sec != null ? formatClock(hit.start_sec) : hit.heading_path}
                </span>
                <span className="line-clamp-3 text-sm leading-7 break-words">
                  <SearchHighlight text={hit.snippet} query={query} mode="fts" />
                </span>
              </>
            )
            return (
              <li key={`${hit.kind}-${hit.chunk_ord}-${index}`}>
                {href ? (
                  <Link
                    href={href}
                    className="grid gap-0.5 rounded-[10px] px-2.5 py-2 hover:bg-lift sm:grid-cols-[88px_minmax(0,1fr)] sm:gap-3"
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="grid gap-0.5 px-2.5 py-2 sm:grid-cols-[88px_minmax(0,1fr)] sm:gap-3">{body}</div>
                )}
              </li>
            )
          })}
        </ul>
      ) : null}
      {rest > 0 ? (
        <Button size="sm" variant="ghost" className="mt-1" onClick={() => setOpen(true)}>
          再显示 {rest} 处命中
        </Button>
      ) : null}
    </article>
  )
}
