import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react'
import {ArrowLeft, BookOpen, Search, Send} from 'lucide-react'
import {Link, useLocation} from 'wouter'
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

export function KnowledgePage() {
  const [, navigate] = useLocation()
  const runtime = useRuntimeConfig()
  const [status, setStatus] = useState<KnowledgeStatus | null>(null)
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<KnowledgeSearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  const chatEnabled = Boolean(runtime?.knowledge_chat_enabled ?? status?.chat_enabled)
  const searchEnabled = Boolean(
    runtime?.knowledge_search_enabled ?? status?.search_enabled ?? true,
  )

  const [chatInput, setChatInput] = useState('')
  const [chatAnswer, setChatAnswer] = useState('')
  const [citations, setCitations] = useState<KnowledgeCitation[]>([])
  const [chatPhase, setChatPhase] = useState<string | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)
  const [chatBusy, setChatBusy] = useState(false)
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

  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim()
    if (!trimmed) {
      setHits([])
      setSearchError(null)
      return
    }
    setSearching(true)
    setSearchError(null)
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

  const onSearchSubmit = (event: FormEvent) => {
    event.preventDefault()
    void runSearch(query)
  }

  const onChatSubmit = (event: FormEvent) => {
    event.preventDefault()
    const q = chatInput.trim()
    if (!q || chatBusy || !chatEnabled) return

    streamRef.current?.close()
    setChatBusy(true)
    setChatAnswer('')
    setCitations([])
    setChatError(null)
    setChatPhase('searching')

    streamRef.current = openKnowledgeChatStream(
      {query: q, limit: 6},
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
  }

  return (
    <div className="grid min-h-[calc(100dvh-3rem)] animate-fade-in-up content-start gap-5 sm:min-h-[calc(100dvh-5rem)]">
      <header className="grid gap-4 px-4 sm:px-5">
        <button
          type="button"
          onClick={() => (window.history.length > 1 ? window.history.back() : navigate('/history'))}
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
          <p className="mt-1 text-sm text-muted">
            检索与问答仅使用本地「AI 视频总结」片段；引用标注为「AI 总结：…」，不会编造时间戳。
          </p>
          {status && (
            <p className="mt-1 text-xs text-muted">
              已登记 {status.documents} 篇 · 索引 {status.chunks} 块
              {status.search_enabled ? '' : ' · 检索未启用'}
              {chatEnabled ? ' · 问答已开启' : ' · 问答关闭'}
            </p>
          )}
        </div>
      </header>

      <section className="grid gap-3 px-4 sm:px-5">
        <div className="flex items-center gap-2 text-sm font-medium text-ink">
          <Search size={15} className="text-muted" />
          总结检索
        </div>
        {!searchEnabled ? (
          <p className="rounded-2xl bg-lift px-4 py-3 text-sm text-muted">知识检索未启用。</p>
        ) : (
          <>
            <form onSubmit={onSearchSubmit} className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
              <label className="relative block min-w-0">
                <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜总结关键词…"
                  className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30"
                />
              </label>
              <button
                type="submit"
                disabled={searching || !query.trim()}
                className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-brand px-4 text-sm text-white shadow-card disabled:opacity-40"
              >
                {searching ? <Spinner size={14} /> : null}
                搜索
              </button>
            </form>
            {searchError && <p className="text-sm text-danger">{searchError}</p>}
            <ul className="grid gap-2">
              {hits.map((hit) => (
                <li key={hit.chunk_id} className="rounded-2xl border border-line/70 bg-panel p-4 shadow-card">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <span className="text-sm font-medium text-ink">{hit.title || '无标题'}</span>
                    {hit.author && <span className="text-xs text-muted">{hit.author}</span>}
                    {hit.bvid && <span className="text-xs text-muted">{hit.bvid}</span>}
                  </div>
                  <p className="mt-1 text-xs text-brand">{hit.heading_path}</p>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{hit.snippet}</p>
                </li>
              ))}
              {!searching && query.trim() && hits.length === 0 && !searchError && (
                <li className="rounded-2xl bg-lift px-4 py-6 text-center text-sm text-muted">无匹配总结片段</li>
              )}
            </ul>
          </>
        )}
      </section>

      <section className="grid gap-3 px-4 pb-8 sm:px-5">
        <div className="flex items-center gap-2 text-sm font-medium text-ink">
          <BookOpen size={15} className="text-muted" />
          基于总结的知识问答
        </div>
        {!chatEnabled ? (
          <p className="rounded-2xl bg-lift px-4 py-3 text-sm text-muted">
            问答默认关闭。在服务端设置 <code className="text-xs">KNOWLEDGE_CHAT_ENABLED=true</code> 后可用；开启后提问与总结片段会发往已配置的 LLM。
          </p>
        ) : (
          <>
            <form onSubmit={onChatSubmit} className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
              <input
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                placeholder="根据已总结的视频提问…"
                disabled={chatBusy}
                className="min-h-11 w-full rounded-2xl bg-lift px-4 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30 disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={chatBusy || !chatInput.trim()}
                className="inline-flex min-h-11 items-center gap-2 rounded-2xl bg-brand px-4 text-sm text-white shadow-card disabled:opacity-40"
                aria-label="发送"
              >
                {chatBusy ? <Spinner size={14} /> : <Send size={15} />}
                提问
              </button>
            </form>
            {chatPhase && (
              <p className="text-xs text-muted">
                {chatPhase === 'searching' && '正在检索总结…'}
                {chatPhase === 'generating' && '正在生成回答…'}
                {chatPhase === 'refuse' && '证据不足'}
              </p>
            )}
            {chatError && <p className="text-sm text-danger">{chatError}</p>}
            {chatAnswer && (
              <div className="rounded-2xl border border-line/70 bg-panel p-4 text-sm shadow-card prose-sm max-w-none text-ink">
                <ReactMarkdown
                  components={{
                    a: ({children}) => <span>{children}</span>,
                    img: ({alt}) => <span>{alt ?? ''}</span>,
                  }}
                >
                  {chatAnswer}
                </ReactMarkdown>
              </div>
            )}
            {citations.length > 0 && (
              <div className="grid gap-2">
                <p className="text-xs font-medium text-muted">引用来源（AI 总结）</p>
                {citations.map((cite) => (
                  <div key={cite.id} className="rounded-2xl bg-lift px-3 py-2 text-sm">
                    <p className="font-medium text-ink">{cite.title || '无标题'}</p>
                    <p className="text-xs text-brand">{cite.heading_path || cite.locator}</p>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        <p className="text-xs text-muted">
          <Link href="/history" className="text-brand hover:underline">
            返回历史
          </Link>
          {' · '}
          检索始终可用（登记开启时）；问答独立开关。
        </p>
      </section>
    </div>
  )
}
