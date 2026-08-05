import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react'
import {
  ChevronDown,
  ChevronUp,
  MessageCircle,
  RotateCcw,
  Search,
  Send,
  Trash2,
} from 'lucide-react'
import {useLocation} from 'wouter'
import ReactMarkdown from 'react-markdown'
import {
  getKnowledgeStatus,
  listKnowledgeDocuments,
  purgeKnowledgeDocument,
  restoreKnowledgeDocument,
  searchKnowledge,
  softDeleteKnowledgeDocument,
  type KnowledgeCitation,
  type KnowledgeDocumentLite,
  type KnowledgeSearchHit,
  type KnowledgeStatus,
} from '../lib/api'
import {openKnowledgeChatStream} from '../lib/sse'
import {PROSE} from '../lib/prose'
import {useRuntimeConfig} from '../hooks/useRuntimeConfig'
import {BackButton} from '../components/BackButton'
import {ConfirmDialog} from '../components/ConfirmDialog'
import {Spinner} from '../components/Spinner'

type QueryMode = 'search' | 'ask'

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
  const [, navigate] = useLocation()
  // fresh: avoid sticky module cache after enabling KNOWLEDGE_CHAT_ENABLED + restart.
  const runtime = useRuntimeConfig({fresh: true})
  const [status, setStatus] = useState<KnowledgeStatus | null>(null)
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<QueryMode>('search')

  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<KnowledgeSearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)

  // Prefer /v1/knowledge/status when loaded; fall back to /v1/config/runtime.
  // Either true enables the ask toggle (status can lag if only runtime refreshed).
  const chatEnabled = Boolean(
    status?.chat_enabled === true || runtime?.knowledge_chat_enabled === true,
  )
  const searchEnabled = Boolean(
    status != null
      ? status.search_enabled
      : (runtime?.knowledge_search_enabled ?? true),
  )
  const activeMode: QueryMode = chatEnabled ? mode : 'search'

  const [chatAnswer, setChatAnswer] = useState('')
  const [citations, setCitations] = useState<KnowledgeCitation[]>([])
  const [chatPhase, setChatPhase] = useState<string | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)
  const [chatBusy, setChatBusy] = useState(false)
  const [hasAsked, setHasAsked] = useState(false)
  const streamRef = useRef<{close: () => void} | null>(null)

  // Secondary: registered documents lifecycle
  const [docs, setDocs] = useState<KnowledgeDocumentLite[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [docsError, setDocsError] = useState<string | null>(null)
  const [showDeleted, setShowDeleted] = useState(false)
  const [docBusyId, setDocBusyId] = useState<string | null>(null)
  const [purgeTarget, setPurgeTarget] = useState<KnowledgeDocumentLite | null>(null)
  const [purgeConfirmText, setPurgeConfirmText] = useState('')
  const [softDeleteTarget, setSoftDeleteTarget] = useState<KnowledgeDocumentLite | null>(null)

  const refreshStatus = useCallback(() => {
    void getKnowledgeStatus()
      .then((value) => setStatus(value))
      .catch(() => setStatus(null))
  }, [])

  const loadDocuments = useCallback(async (includeDeleted: boolean) => {
    setDocsLoading(true)
    setDocsError(null)
    try {
      const result = await listKnowledgeDocuments(includeDeleted)
      setDocs(result.documents)
    } catch (err) {
      setDocs([])
      setDocsError(err instanceof Error ? err.message : '加载文档列表失败')
    } finally {
      setDocsLoading(false)
    }
  }, [])

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
    void loadDocuments(showDeleted)
  }, [loadDocuments, showDeleted])

  useEffect(() => {
    return () => {
      streamRef.current?.close()
    }
  }, [])

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

  const runChat = useCallback(
    (q: string) => {
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
    },
    [chatBusy, chatEnabled],
  )

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

  const runAsSearch = () => {
    setMode('search')
    const q = query.trim()
    if (!q) return
    void runSearch(q)
  }

  const runAsAsk = () => {
    if (!chatEnabled) return
    setMode('ask')
    const q = query.trim()
    if (!q) return
    runChat(q)
  }

  const busy = activeMode === 'ask' ? chatBusy : searching
  const isAsk = activeMode === 'ask'
  const placeholder = isAsk
    ? '根据已总结与转写的视频提问…'
    : '搜总结或转写里的关键词、数字、术语…'

  const subtitle = chatEnabled
    ? '右侧「搜索」查片段，「提问」用已登记总结/转写做问答（会调用 LLM）。'
    : '在 AI 总结与转写片段中检索；列表默认显示摘录，可展开全文。'

  const purgeExpected =
    (purgeTarget?.title || '').trim() || (purgeTarget?.bvid || '').trim()
  const purgeMatches =
    purgeConfirmText.trim() === purgeExpected && purgeExpected.length > 0

  const handleSoftDelete = async () => {
    if (!softDeleteTarget) return
    setDocBusyId(softDeleteTarget.id)
    try {
      await softDeleteKnowledgeDocument(softDeleteTarget.id)
      setSoftDeleteTarget(null)
      await loadDocuments(showDeleted)
      refreshStatus()
    } catch (err) {
      setDocsError(err instanceof Error ? err.message : '软删除失败')
    } finally {
      setDocBusyId(null)
    }
  }

  const handleRestore = async (doc: KnowledgeDocumentLite) => {
    setDocBusyId(doc.id)
    setDocsError(null)
    try {
      await restoreKnowledgeDocument(doc.id)
      await loadDocuments(showDeleted)
      refreshStatus()
    } catch (err) {
      setDocsError(err instanceof Error ? err.message : '恢复失败')
    } finally {
      setDocBusyId(null)
    }
  }

  const handlePurge = async () => {
    if (!purgeTarget || !purgeMatches) return
    setDocBusyId(purgeTarget.id)
    try {
      await purgeKnowledgeDocument(purgeTarget.id, purgeConfirmText.trim())
      setPurgeTarget(null)
      setPurgeConfirmText('')
      await loadDocuments(showDeleted)
      refreshStatus()
    } catch (err) {
      setDocsError(err instanceof Error ? err.message : '永久删除失败')
    } finally {
      setDocBusyId(null)
    }
  }

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
              {(status.documents_deleted ?? 0) > 0 && (
                <>
                  <span className="text-muted/50"> · </span>
                  回收站 {status.documents_deleted}
                </>
              )}
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
                className={`grid gap-2 ${
                  chatEnabled
                    ? 'grid-cols-1 sm:grid-cols-[minmax(0,1fr)_auto_auto]'
                    : 'grid-cols-[minmax(0,1fr)_auto]'
                }`}
              >
                <label className="relative block min-w-0">
                  <Search
                    size={15}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
                  />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={
                      chatEnabled
                        ? '输入关键词搜索，或点右侧「提问」做知识问答…'
                        : placeholder
                    }
                    disabled={busy}
                    className="min-h-11 w-full rounded-2xl bg-lift py-2 pl-10 pr-3 text-sm outline-none placeholder:text-muted/55 focus:ring-2 focus:ring-brand/30 disabled:opacity-60"
                  />
                </label>
                {chatEnabled ? (
                  <>
                    <button
                      type="button"
                      onClick={runAsSearch}
                      disabled={busy || !query.trim()}
                      className="inline-flex min-h-11 min-w-[5.5rem] items-center justify-center gap-2 rounded-2xl bg-lift px-4 text-sm font-medium text-ink ring-1 ring-line/80 disabled:opacity-40"
                    >
                      {searching ? <Spinner size={14} /> : <Search size={15} />}
                      搜索
                    </button>
                    <button
                      type="button"
                      onClick={runAsAsk}
                      disabled={busy || !query.trim()}
                      className="inline-flex min-h-11 min-w-[5.5rem] items-center justify-center gap-2 rounded-2xl bg-brand px-4 text-sm font-medium text-white shadow-card disabled:opacity-40"
                    >
                      {chatBusy ? <Spinner size={14} /> : <MessageCircle size={15} />}
                      提问
                    </button>
                  </>
                ) : (
                  <button
                    type="submit"
                    disabled={busy || !query.trim()}
                    className="inline-flex min-h-11 min-w-[5.5rem] items-center justify-center gap-2 rounded-2xl bg-brand px-4 text-sm font-medium text-white shadow-card disabled:opacity-40"
                  >
                    {busy ? <Spinner size={14} /> : <Search size={15} />}
                    搜索
                  </button>
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
                </>
              )}

              {activeMode === 'ask' && (
                <>
                  {chatPhase && (
                    <div className="mb-3 flex flex-wrap items-center gap-3">
                      <p className="text-sm text-muted">
                        {chatPhase === 'searching' && '正在检索总结与转写…'}
                        {chatPhase === 'generating' && '正在生成回答…'}
                        {chatPhase === 'refuse' && '证据不足'}
                      </p>
                      {chatBusy && (
                        <button
                          type="button"
                          onClick={() => {
                            streamRef.current?.close()
                            setChatBusy(false)
                            setChatPhase(null)
                          }}
                          className="inline-flex min-h-8 items-center gap-1.5 rounded-xl bg-lift px-3 text-xs text-muted transition hover:bg-line/70 hover:text-ink"
                        >
                          停止
                        </button>
                      )}
                    </div>
                  )}
                  {chatError && <p className="mb-3 text-sm text-danger">{chatError}</p>}
                  {chatAnswer && (
                    <div className={`mb-3 rounded-2xl border border-line/70 bg-panel p-4 shadow-card ${PROSE}`}>
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
                          <p className="mt-1 text-sm text-brand">{cite.locator || cite.heading_path}</p>
                          {cite.source_level === 'transcript' && cite.subtitle_source === 'asr' && (
                            <p className="mt-1 text-xs text-warning">ASR 转写，可能存在识别误差</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {!chatBusy && !hasAsked && !chatError && (
                    <p className="py-10 text-center text-sm text-muted">
                      用自然语言提问；回答依据本地 AI 总结与转写证据
                    </p>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </section>

      <section className="min-w-0 border-t border-line/70 px-4 pb-12 pt-6 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-ink">已登记文档</h2>
            <p className="mt-1 text-sm text-muted">
              软删除会从检索中隐藏并保留产物；永久删除不可恢复。
            </p>
          </div>
          <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-2xl bg-lift px-3 text-sm text-muted">
            <input
              type="checkbox"
              checked={showDeleted}
              onChange={(event) => setShowDeleted(event.target.checked)}
              className="rounded border-line"
            />
            显示已删除
          </label>
        </div>

        {docsError && <p className="mt-3 text-sm text-danger">{docsError}</p>}
        {docsLoading && <p className="mt-6 text-center text-sm text-muted">加载文档…</p>}
        {!docsLoading && docs.length === 0 && !docsError && (
          <p className="mt-6 rounded-2xl bg-lift px-4 py-6 text-center text-sm text-muted">
            {showDeleted ? '没有已删除的文档' : '尚无已登记文档'}
          </p>
        )}
        {!docsLoading && docs.length > 0 && (
          <ul className="mt-4 grid min-w-0 gap-2">
            {docs.map((doc) => {
              const deleted = doc.deleted_at != null
              const rowBusy = docBusyId === doc.id
              return (
                <li
                  key={doc.id}
                  className="grid min-w-0 gap-3 rounded-2xl border border-line/70 bg-panel px-4 py-3 shadow-card sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                >
                  <div className="min-w-0 overflow-hidden">
                    <div className="flex min-w-0 items-center gap-2">
                      <p className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
                        {doc.title || '无标题'}
                      </p>
                      {deleted && (
                        <span className="shrink-0 rounded-full bg-lift px-2 py-0.5 text-xs text-muted">
                          已删除
                        </span>
                      )}
                    </div>
                    <p className="mt-1 flex min-w-0 items-center gap-x-2 overflow-hidden text-xs text-muted">
                      {doc.author && (
                        <span className="min-w-0 truncate">{doc.author}</span>
                      )}
                      {doc.author && doc.bvid && <span className="shrink-0">·</span>}
                      {doc.bvid && (
                        <span className="min-w-0 shrink truncate font-mono">{doc.bvid}</span>
                      )}
                    </p>
                  </div>
                  <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">
                    {deleted ? (
                      <>
                        <button
                          type="button"
                          disabled={rowBusy}
                          onClick={() => void handleRestore(doc)}
                          className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-xl bg-lift px-3 text-sm text-ink transition hover:bg-line/70 disabled:opacity-40"
                        >
                          <RotateCcw size={14} />
                          恢复
                        </button>
                        <button
                          type="button"
                          disabled={rowBusy}
                          onClick={() => {
                            setPurgeTarget(doc)
                            setPurgeConfirmText('')
                          }}
                          className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-xl bg-danger/10 px-3 text-sm text-danger transition hover:bg-danger/15 disabled:opacity-40"
                        >
                          <Trash2 size={14} />
                          永久删除
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          disabled={rowBusy}
                          onClick={() => setSoftDeleteTarget(doc)}
                          className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-xl bg-lift px-3 text-sm text-muted transition hover:bg-line/70 hover:text-ink disabled:opacity-40"
                        >
                          <Trash2 size={14} />
                          删除
                        </button>
                        <button
                          type="button"
                          disabled={rowBusy}
                          onClick={() => {
                            setPurgeTarget(doc)
                            setPurgeConfirmText('')
                          }}
                          className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-xl px-3 text-sm text-danger/80 transition hover:bg-danger/10 disabled:opacity-40"
                        >
                          永久删除
                        </button>
                      </>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <ConfirmDialog
        open={softDeleteTarget != null}
        title="从知识库中移除？"
        description={
          softDeleteTarget ? (
            <>
              「{softDeleteTarget.title || softDeleteTarget.bvid || '无标题'}」将从检索中隐藏，产物保留约 30
              天，可随时恢复。
            </>
          ) : null
        }
        confirmLabel="软删除"
        danger
        loading={softDeleteTarget != null && docBusyId === softDeleteTarget.id}
        onConfirm={() => void handleSoftDelete()}
        onCancel={() => setSoftDeleteTarget(null)}
      />

      <ConfirmDialog
        open={purgeTarget != null}
        title="永久删除文档？"
        description={
          purgeTarget ? (
            <div className="grid gap-3">
              <p>
                将删除磁盘产物、全部修订与索引，且不可恢复。请输入文档标题或 bvid 以确认：
              </p>
              <p className="break-all rounded-xl bg-lift px-3 py-2 font-mono text-xs text-ink">
                {purgeExpected || '（无标题也无 bvid）'}
              </p>
              <input
                value={purgeConfirmText}
                onChange={(event) => setPurgeConfirmText(event.target.value)}
                placeholder="输入标题或 bvid"
                className="min-h-10 w-full rounded-xl bg-lift px-3 text-sm text-ink outline-none focus:ring-2 focus:ring-brand/30"
                autoComplete="off"
              />
            </div>
          ) : null
        }
        confirmLabel="永久删除"
        danger
        loading={purgeTarget != null && docBusyId === purgeTarget.id}
        confirmDisabled={!purgeMatches}
        onConfirm={() => void handlePurge()}
        onCancel={() => {
          setPurgeTarget(null)
          setPurgeConfirmText('')
        }}
      />
    </div>
  )
}
