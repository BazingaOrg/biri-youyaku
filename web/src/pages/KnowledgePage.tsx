import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowLeft, ChevronDown, ChevronUp, Search, Send} from 'lucide-react'
import {useLocation} from 'wouter'
import ReactMarkdown from 'react-markdown'
import {
  getKnowledgeStatus,
  searchKnowledge,
  type KnowledgeCitation,
  type KnowledgeSearchHit,
  type KnowledgeStatus,
} from '../lib/api'
import {openKnowledgeChatStream} from '../lib/sse'
import {useRuntimeConfig} from '../hooks/useRuntimeConfig'
import {Spinner} from '../components/Spinner'

type QueryMode = 'search' | 'ask'

function HitCard({hit}: {hit: KnowledgeSearchHit}) {
  const full = (hit.chunk_text || hit.snippet || '').trim()
  const preview = (hit.snippet || full).trim()
  const needsExpand = full.length > preview.length || full.length > 160
  const [open, setOpen] = useState(false)
  const body = open ? full : preview

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
      <p className="mt-2 text-xs font-medium text-brand">{hit.heading_path}</p>
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
  const [, navigate] = useLocation()
  const runtime = useRuntimeConfig()
  const [status, setStatus] = useState<KnowledgeStatus | null>(null)
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<QueryMode>('search')

  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<KnowledgeSearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)

  const chatEnabled = Boolean(runtime?.knowledge_chat_enabled ?? status?.chat_enabled)
  const searchEnabled = Boolean(
    runtime?.knowledge_search_enabled ?? status?.search_enabled ?? true,
  )
  // When chat is off, always stay in search mode and hide the switcher.
  const activeMode: QueryMode = chatEnabled ? mode : 'search'

  const [chatAnswer, setChatAnswer] = useState('')
  const [citations, setCitations] = useState<KnowledgeCitation[]>([])
  const [chatPhase, setChatPhase] = useState<string | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)
  const [chatBusy, setChatBusy] = useState(false)
  const [hasAsked, setHasAsked] = useState(false)
  const streamRef = useRef<{close: () => void} | null>(null)

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

  useEffect(() => {
    return () => {
      streamRef.current?.close()
    }
  }, [])

  // If chat gets disabled at runtime, force search mode.
  useEffect(() => {
    if (!chatEnabled && mode === 'ask') {
      setMode('search')
    }
  }, [chatEnabled, mode])

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
    setChatAnswer('')
    setCitations([])
    setChatError(null)
    setHasAsked(false)
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

  const runChat = useCallback((q: string) => {
    const trimmed = q.trim()
    if (!trimmed || chatBusy || !chatEnabled) return

    streamRef.current?.close()
    setChatBusy(true)
    setChatAnswer('')
    setCitations([])
    setChatError(null)
    setChatPhase('searching')
    setHasAsked(true)
    setHits([])
    setSearchError(null)
    setHasSearched(false)

    streamRef.current = openKnowledgeChatStream(
      {query: trimmed, limit: 6},
      (message) => {
        let payload: Record<string, unknown> = {}
        try {
          payload = JSON.parse(message.data) as Record<string, unknown>
        } catch {
          payload = {}
        }
        if (message.event === 'status') {
          setChatPhase(typeof payload.phase === 'string' ? payload.phase : null)
        } else if (message.event === 'delta') {
          if (typeof payload.text === 'string') setChatAnswer(payload.text)
        } else if (message.event === 'citations') {
          const list = payload.citations
          if (Array.isArray(list)) {
            setCitations(list as KnowledgeCitation[])
          }
        } else if (message.event === 'error') {
          setChatError(typeof payload.message === 'string' ? payload.message : '问答失败')
          setChatBusy(false)
          setChatPhase(null)
        } else if (message.event === 'done') {
          if (typeof payload.text === 'string' && payload.text) {
            setChatAnswer(payload.text)
          }
          setChatBusy(false)
          setChatPhase(null)
        }
      },
      (error) => {
        setChatError(error.message)
        setChatBusy(false)
        setChatPhase(null)
      },
      () => {
        setChatBusy(false)
      },
    )
  }, [chatBusy, chatEnabled])

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const q = query.trim()
    if (!q) return
    if (activeMode === 'ask') {
      runChat(q)
    } else {
      void runSearch(q)
    }
  }

  const busy = activeMode === 'ask' ? chatBusy : searching
  const submitLabel = activeMode === 'ask' ? '提问' : '搜索'
  const placeholder =
    activeMode === 'ask'
      ? '根据已总结的视频提问…'
      : '搜总结里的关键词、人名、术语…'

  const subtitle = chatEnabled
    ? '在已总结的笔记中检索，或切换到提问让 AI 基于命中片段作答。'
    : '在已总结的视频笔记里检索；列表默认显示摘录，可展开全文。'

  return (
    <div className="grid min-h-[calc(100dvh-3rem)] animate-fade-in-up content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
      <header className="grid gap-4 px-4 sm:px-5">
        <button
          type="button"
          onClick={() => (window.history.length > 1 ? window.history.back() : navigate('/'))}
          className="inline-flex min-h-10 w-fit items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted transition-[transform,background-color,color] hover:bg-line/70 hover:text-ink active:scale-95"
        >
          <ArrowLeft size={16} />
          返回
        </button>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-[-0.012em] text-ink sm:text-3xl">知识库</h1>
            <span className="rounded-full bg-brandSoft px-2.5 py-0.5 text-xs text-brand">基于总结</span>
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
              <form onSubmit={onSubmit} className="grid gap-3">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                  <label className="relative block min-w-0">
                    <Search
                      size={15}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
                    />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder={placeholder}
                      disabled={busy}
                      className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30 disabled:opacity-60"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={busy || !query.trim()}
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-2xl bg-brand px-4 text-sm font-medium text-white shadow-card disabled:opacity-40"
                  >
                    {busy ? (
                      <Spinner size={14} />
                    ) : activeMode === 'ask' ? (
                      <Send size={15} />
                    ) : null}
                    {submitLabel}
                  </button>
                </div>

                {chatEnabled && (
                  <div className="flex flex-wrap items-center gap-3">
                    <div
                      className="inline-flex rounded-2xl bg-lift p-1"
                      role="group"
                      aria-label="查询方式"
                    >
                      <button
                        type="button"
                        onClick={() => setMode('search')}
                        className={`min-h-9 rounded-xl px-3 text-sm transition ${
                          activeMode === 'search'
                            ? 'bg-panel font-medium text-ink shadow-card'
                            : 'text-muted hover:text-ink'
                        }`}
                      >
                        检索
                      </button>
                      <button
                        type="button"
                        onClick={() => setMode('ask')}
                        className={`min-h-9 rounded-xl px-3 text-sm transition ${
                          activeMode === 'ask'
                            ? 'bg-panel font-medium text-ink shadow-card'
                            : 'text-muted hover:text-ink'
                        }`}
                      >
                        提问
                      </button>
                    </div>
                    <p className="text-sm text-muted">
                      {activeMode === 'search'
                        ? '直接在总结片段中匹配关键词。'
                        : '先检索相关总结，再交给已配置的 LLM 作答。'}
                    </p>
                  </div>
                )}
              </form>
            </div>

            <div className="py-3 pb-10">
              {activeMode === 'search' && (
                <>
                  {searchError && <p className="mb-3 text-sm text-danger">{searchError}</p>}
                  {searching && <p className="py-8 text-center text-sm text-muted">检索中…</p>}
                  {!searching && hasSearched && hits.length === 0 && !searchError && (
                    <p className="border-b border-line/60 py-12 text-center text-sm text-muted">
                      没有匹配的总结片段，试试更具体的词
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
                      输入关键词，在已总结的笔记中查找
                    </p>
                  )}
                </>
              )}

              {activeMode === 'ask' && (
                <>
                  {chatPhase && (
                    <p className="mb-3 text-sm text-muted">
                      {chatPhase === 'searching' && '正在检索总结…'}
                      {chatPhase === 'generating' && '正在生成回答…'}
                      {chatPhase === 'refuse' && '证据不足'}
                    </p>
                  )}
                  {chatError && <p className="mb-3 text-sm text-danger">{chatError}</p>}
                  {chatAnswer && (
                    <div className="mb-3 rounded-2xl border border-line/70 bg-panel p-4 text-sm leading-6 text-ink shadow-card">
                      <ReactMarkdown
                        components={{
                          a: ({children}) => <span>{children}</span>,
                          img: ({alt}) => <span>{alt ?? ''}</span>,
                          p: ({children}) => <p className="mb-2 last:mb-0">{children}</p>,
                        }}
                      >
                        {chatAnswer}
                      </ReactMarkdown>
                    </div>
                  )}
                  {citations.length > 0 && (
                    <div className="grid gap-2">
                      <p className="text-sm font-medium text-ink">引用来源</p>
                      {citations.map((cite) => (
                        <div key={cite.id} className="rounded-2xl bg-lift px-4 py-3">
                          <p className="text-sm font-medium text-ink">{cite.title || '无标题'}</p>
                          <p className="mt-1 text-sm text-brand">{cite.heading_path || cite.locator}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {!chatBusy && !hasAsked && !chatError && (
                    <p className="py-10 text-center text-sm text-muted">
                      用自然语言提问；回答仅依据本地 AI 视频总结
                    </p>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
