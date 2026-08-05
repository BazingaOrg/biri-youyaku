import {useCallback, useEffect, useState, type FormEvent} from 'react'
import {ChevronDown, ChevronUp, Search} from 'lucide-react'
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

function locatorLabel(hit: KnowledgeSearchHit): string {
  if (hit.locator) return hit.locator
  if (hit.source_level === 'transcript' && hit.start_sec != null && hit.end_sec != null) {
    const fmt = (sec: number) => {
      const total = Math.max(0, Math.floor(sec))
      const m = Math.floor(total / 60)
      const s = total % 60
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    }
    return `转写：${fmt(hit.start_sec)}–${fmt(hit.end_sec)}`
  }
  return hit.heading_path || 'AI 总结'
}

function HitCard({hit}: {hit: KnowledgeSearchHit}) {
  const full = (hit.chunk_text || hit.snippet || '').trim()
  const snippet = (hit.snippet || '').trim()
  // Only show expand when the backend sent a truncated snippet that differs from
  // the full chunk_text.  If there is no snippet (preview === full), the toggle
  // would flip between two identical strings.
  const needsExpand = Boolean(snippet) && full.length > snippet.length
  const [open, setOpen] = useState(false)
  const body = open ? full : (snippet || full)
  const label = locatorLabel(hit)
  const isTranscript = hit.source_level === 'transcript'
  const asrRisk = isTranscript && hit.subtitle_source === 'asr'

  return (
    <li className="rounded-2xl border border-line/70 bg-panel p-4 shadow-card">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">{hit.title || '无标题'}</p>
        <p className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
          {hit.author && <span className="truncate">{hit.author}</span>}
          {hit.author && hit.bvid && <span>·</span>}
          {hit.bvid && <span className="font-mono">{hit.bvid}</span>}
        </p>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            isTranscript
              ? 'bg-lift text-ink ring-1 ring-line/80'
              : 'bg-brandSoft text-brand'
          }`}
        >
          {label}
        </span>
        {asrRisk && (
          <span className="text-xs text-warning">ASR 转写，可能存在识别误差</span>
        )}
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

  const subtitle = '在 AI 总结与转写片段中检索；列表默认显示摘录，可展开全文。'

  return (
    <div className="grid min-h-[calc(100dvh-3rem)] min-w-0 animate-fade-in-up content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
      <header className="grid gap-4 px-4 sm:px-5">
        <BackButton />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">知识库</h1>
            <span className="rounded-full bg-brandSoft px-2.5 py-0.5 text-xs text-brand">总结 + 转写</span>
          </div>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
          {status && (
            <p className="mt-2 text-sm text-muted">
              已登记 {status.documents} 篇
              <span className="text-muted/50"> · </span>
              索引 {status.chunks} 块
              {!status.search_enabled && (
                <>
                  <span className="text-muted/50"> · </span>
                  <span className="text-warning">检索未启用</span>
                </>
              )}
            </p>
          )}
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
                    placeholder="搜总结或转写里的关键词、数字、术语…"
                    disabled={searching}
                    className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30 disabled:opacity-60"
                  />
                </label>
                <button
                  type="submit"
                  disabled={searching || !query.trim()}
                  className="inline-flex min-h-11 min-w-[5.5rem] items-center justify-center gap-2 rounded-2xl bg-brand px-4 text-sm font-medium text-white shadow-card disabled:opacity-40"
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
                  {hits.map((hit) => (
                    <HitCard key={hit.chunk_id} hit={hit} />
                  ))}
                </ul>
              )}
              {!searching && !hasSearched && !searchError && (
                <p className="py-10 text-center text-sm text-muted">
                  输入关键词，在 AI 总结与转写片段中查找
                </p>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
