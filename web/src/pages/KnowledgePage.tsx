import {useCallback, useEffect, useMemo, useState, type FormEvent} from 'react'
import {ChevronDown, ChevronUp, ExternalLink, Search} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import {
  getKnowledgeStatus,
  searchKnowledge,
  type KnowledgeSearchHit,
  type KnowledgeStatus,
} from '../lib/api'
import {PROSE} from '../lib/prose'
import {useRuntimeConfig} from '../hooks/useRuntimeConfig'
import {BackButton} from '../components/BackButton'
import {Spinner} from '../components/Spinner'

function formatTimestamp(sec: number) {
  const total = Math.max(0, Math.floor(sec))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function locatorLabel(hit: KnowledgeSearchHit): string {
  if (hit.locator) return hit.locator
  if (hit.source_level === 'transcript' && hit.start_sec != null && hit.end_sec != null) {
    return `转写：${formatTimestamp(hit.start_sec)}–${formatTimestamp(hit.end_sec)}`
  }
  return hit.heading_path || 'AI 总结'
}

function sourceUrl(hit: KnowledgeSearchHit) {
  if (!hit.source_url) return null
  if (hit.source_level !== 'transcript' || hit.start_sec == null) return hit.source_url
  try {
    const url = new URL(hit.source_url)
    url.searchParams.set('t', String(Math.floor(hit.start_sec)))
    return url.toString()
  } catch {
    return hit.source_url
  }
}

function HitSnippet({hit}: {hit: KnowledgeSearchHit}) {
  const full = (hit.chunk_text || hit.snippet || '').trim()
  const snippet = (hit.snippet || '').trim()
  const needsExpand = Boolean(snippet) && full.length > snippet.length
  const [open, setOpen] = useState(false)
  const body = open ? full : (snippet || full)
  const label = locatorLabel(hit)
  const isTranscript = hit.source_level === 'transcript'
  const videoUrl = sourceUrl(hit)

  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            isTranscript
              ? 'bg-lift text-ink ring-1 ring-line/80'
              : 'bg-brandSoft text-brand'
          }`}
        >
          {label}
        </span>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink/90">{body}</p>
      {needsExpand && (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="mt-2 inline-flex min-h-9 items-center gap-1 rounded-xl px-2 text-sm text-muted transition hover:bg-lift hover:text-ink"
        >
          {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          {open ? '收起' : '展开全文'}
        </button>
      )}
      {videoUrl && (
        <a
          href={videoUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-xl px-2 text-sm text-muted transition hover:bg-lift hover:text-ink"
        >
          {isTranscript && hit.start_sec != null ? `打开视频 ${formatTimestamp(hit.start_sec)}` : '打开视频'}
          <ExternalLink size={14} />
        </a>
      )}
    </div>
  )
}

function HitCard({hits}: {hits: KnowledgeSearchHit[]}) {
  const first = hits[0]
  return (
    <li className="rounded-2xl border border-line/70 bg-panel p-4 shadow-card">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">{first.title || '无标题'}</p>
        {first.author && <p className="mt-1 truncate text-xs text-muted">{first.author}</p>}
      </div>
      <div className="mt-3 divide-y divide-line/60">
        {hits.map((hit) => <HitSnippet key={hit.chunk_id} hit={hit} />)}
      </div>
    </li>
  )
}

export function KnowledgePage() {
  const runtime = useRuntimeConfig()
  const [status, setStatus] = useState<KnowledgeStatus | null>(null)
  const [query, setQuery] = useState('')

  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<KnowledgeSearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const groupedHits = useMemo(() => {
    const groups = new Map<string, KnowledgeSearchHit[]>()
    for (const hit of hits) groups.set(hit.document_id, [...(groups.get(hit.document_id) ?? []), hit])
    return [...groups.values()]
  }, [hits])

  const searchEnabled = Boolean(
    status != null
      ? status.search_enabled
      : (runtime?.knowledge_search_enabled ?? true),
  )

  useEffect(() => {
    let cancelled = false
    void getKnowledgeStatus()
      .then((value) => {
        if (!cancelled) setStatus(value)
      })
      .catch(() => {
        if (!cancelled) setStatus(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim()
    if (!trimmed) {
      setHits([])
      setSearchError(null)
      setHasSearched(false)
      return
    }
    setSearching(true)
    setSearchError(null)
    setHasSearched(true)
    try {
      const result = await searchKnowledge(trimmed, 12)
      setHits(result.hits)
    } catch (err) {
      setHits([])
      setSearchError(err instanceof Error ? err.message : '检索失败')
    } finally {
      setSearching(false)
    }
  }, [])

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const q = query.trim()
    if (!q) return
    void runSearch(q)
  }

  return (
    <div className="grid min-h-[calc(100dvh-3rem)] min-w-0 animate-fade-in-up content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
      <header className="grid gap-4 px-4 sm:px-5">
        <BackButton />
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">知识库</h1>
          <p className="mt-1 text-sm text-muted">搜索看过的视频笔记与字幕。</p>
        </div>
      </header>

      <section className="min-w-0 px-4 sm:px-5">
        {!searchEnabled ? (
          <p className="rounded-2xl bg-lift px-4 py-3 text-sm text-muted">知识检索未启用。</p>
        ) : (
          <>
            <div className="border-y border-line/70 py-3">
              <form
                onSubmit={onSubmit}
                className="grid grid-cols-[minmax(0,1fr)_auto] gap-2"
              >
                <label className="relative block min-w-0">
                  <Search
                    size={15}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
                  />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索笔记或字幕…"
                    disabled={searching}
                    className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30 disabled:opacity-60"
                  />
                </label>
                <button
                  type="submit"
                  disabled={searching || !query.trim()}
                  className="inline-flex min-h-11 min-w-[5.5rem] items-center justify-center gap-2 rounded-2xl bg-brandSolid px-4 text-sm font-medium text-onBrand shadow-card disabled:opacity-40"
                >
                  {searching ? <Spinner size={14} /> : <Search size={15} />}
                  搜索
                </button>
              </form>
            </div>

            <div className="py-3 pb-10">
              {searchError && <p className="mb-3 text-sm text-danger">{searchError}</p>}
              {searching && <p className="py-8 text-center text-sm text-muted">检索中…</p>}
              {!searching && hasSearched && hits.length === 0 && !searchError && (
                <p className="border-b border-line/60 py-12 text-center text-sm text-muted">
                  没有匹配的总结或转写片段，试试更具体的词
                </p>
              )}
              {!searching && hits.length > 0 && (
                <ul className="grid gap-3">
                  {groupedHits.map((group) => (
                    <HitCard key={group[0].document_id} hits={group} />
                  ))}
                </ul>
              )}
              {!searching && !hasSearched && !searchError && (
                <p className="py-10 text-center text-sm text-muted">
                  输入关键词，找回笔记和字幕中的内容
                </p>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
