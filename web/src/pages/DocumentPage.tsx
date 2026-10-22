import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Link} from 'wouter'
import {ChevronLeft, ChevronRight, Copy, ExternalLink, MoreHorizontal} from 'lucide-react'
import {
  ApiError,
  biliPlayUrl,
  createJob,
  getJob,
  getLibraryDocumentContent,
  purgeDocument,
  restoreDocument,
  resummarizeJob,
  softDeleteDocument,
  type Job,
  type LibraryDocumentContent,
} from '../lib/api'
import {formatClock, formatDuration} from '../lib/format'
import {transcriptToPlainText} from '../lib/subtitle'
import {backTarget} from '../lib/docNav'
import {useUrlState} from '../hooks/useUrlState'
import {useToast} from '../components/ToastProvider'
import {BackButton} from '../components/BackButton'
import {Button} from '../components/Button'
import {ConfirmDialog} from '../components/ConfirmDialog'
import {LazyMarkdown} from '../components/LazyMarkdown'
import {MarkdownContent} from '../components/MarkdownContent'
import {SearchHighlight} from '../components/SearchHighlight'
import {PROSE} from '../lib/prose'
import {Segmented} from '../components/Segmented'
import {Rabbit} from '../components/Rabbit'
import {PageLoading} from '../components/Spinner'
import {includesSearchQuery} from '../lib/searchHighlight'
import {writeActive} from '../lib/activeJob'

type Tab = 'notes' | 'subs'

export function DocumentPage({id}: {id: string}) {
  const {get, setParams, navigate} = useUrlState()
  const toast = useToast()
  const tab = (get('tab') === 'subs' ? 'subs' : 'notes') as Tab
  const at = get('at')
  const from = get('from')
  const q = from === 'search' ? get('q') : ''
  const [content, setContent] = useState<LibraryDocumentContent | null>(null)
  const [legacyJob, setLegacyJob] = useState<Job | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [removeOpen, setRemoveOpen] = useState(false)
  const [purgeOpen, setPurgeOpen] = useState(false)
  const [purgeInput, setPurgeInput] = useState('')
  const [busy, setBusy] = useState(false)
  const findIndexRef = useRef(0)
  const [findIndex, setFindIndex] = useState(0)
  const [findTotal, setFindTotal] = useState(0)

  const loadGeneration = useRef(0)
  const loadAbort = useRef<AbortController | null>(null)
  const load = useCallback(async () => {
    loadAbort.current?.abort()
    const controller = new AbortController()
    loadAbort.current = controller
    const token = ++loadGeneration.current
    setLoading(true)
    setError(null)
    try {
      const body = await getLibraryDocumentContent(id, {signal: controller.signal})
      if (token !== loadGeneration.current) return
      setContent(body)
      setLegacyJob(null)
    } catch (err) {
      if (token !== loadGeneration.current || controller.signal.aborted) return
      if (err instanceof ApiError && err.status === 404) {
        try {
          const response = await getJob(id)
          if (token !== loadGeneration.current) return
          setLegacyJob(response.job)
          setContent(null)
        } catch (jobErr) {
          if (token !== loadGeneration.current) return
          setError(jobErr instanceof Error ? jobErr.message : '这篇笔记不存在或已移除')
        }
      } else {
        setError(err instanceof Error ? err.message : '加载失败')
      }
    } finally {
      if (token === loadGeneration.current) setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
    return () => {
      loadGeneration.current += 1
      loadAbort.current?.abort()
    }
  }, [load])

  const doc = content?.document
  const markdown = content?.summary.markdown || legacyJob?.summary || ''
  const cues = content?.transcript?.length ? content.transcript : (legacyJob?.transcript ?? [])
  const chunks = content?.note_chunks ?? []
  const bvid = doc?.bvid || legacyJob?.bvid
  const sourceUrl = doc?.source_url || legacyJob?.url
  const deleted = Boolean(doc?.deleted_at)
  const missingFile =
    doc?.legacy_reason === 'summary_file_missing' || Boolean(legacyJob && !legacyJob.summary)
  const legacy = Boolean(doc?.legacy || (!content && legacyJob) || doc?.legacy_reason)
  const daysLeft = doc?.expires_at != null ? Math.max(0, Math.ceil((doc.expires_at - Date.now()) / 86_400_000)) : null

  const back = backTarget({
    from,
    q: get('q'),
    scope: get('scope'),
    up: get('up') || (doc?.mid != null ? String(doc.mid) : ''),
    tag: get('tag'),
    author: doc?.author || legacyJob?.author,
  })

  useEffect(() => {
    if (loading) return
    if (!at) {
      setStale(false)
      return
    }
    const target =
      tab === 'subs'
        ? document.getElementById(`cue-${at}`) || document.querySelector<HTMLElement>(`[data-sec="${at}"]`)
        : document.getElementById(`chunk-${at}`)
    if (!target) {
      setStale(true)
      return
    }
    setStale(false)
    target.scrollIntoView({block: 'center'})
  }, [at, loading, tab, markdown, cues.length, chunks.length])

  useEffect(() => {
    if (!q) {
      setFindTotal(0)
      return
    }
    const nodes = [...document.querySelectorAll<HTMLElement>('[data-find-hit]')]
    setFindTotal(nodes.length)
    const currentAt = nodes.findIndex((node) => node.id === (tab === 'subs' ? `cue-${at}` : `chunk-${at}`))
    const index = currentAt >= 0 ? currentAt : 0
    findIndexRef.current = index
    setFindIndex(index)
    nodes.forEach((node, i) => node.classList.toggle('ring-2', i === index))
  }, [at, q, tab, markdown, cues.length, chunks.length, loading])

  const jumpFind = (delta: number) => {
    const nodes = [...document.querySelectorAll<HTMLElement>('[data-find-hit]')]
    if (nodes.length === 0) return
    const next = (findIndexRef.current + delta + nodes.length) % nodes.length
    findIndexRef.current = next
    setFindIndex(next)
    nodes.forEach((node, i) => node.classList.toggle('ring-2', i === next))
    nodes[next]?.scrollIntoView({block: 'center'})
  }

  const copyCurrent = async () => {
    const text = tab === 'notes' ? markdown : transcriptToPlainText(cues)
    if (!text.trim()) return
    try {
      await navigator.clipboard.writeText(text)
      toast.success(tab === 'notes' ? '笔记已复制' : '字幕已复制')
    } catch {
      toast.error('复制失败', '请手动选中复制')
    }
  }

  const regenerate = async () => {
    setBusy(true)
    try {
      const jobId = doc?.job_id || legacyJob?.id
      if (jobId) {
        const response = await resummarizeJob(jobId, {task_type: 'summary'})
        writeActive({jobId: response.job_id, url: sourceUrl || ''})
        toast.success('已开始重新生成笔记')
        navigate(`/jobs/${response.job_id}`)
        return
      }
      if (!sourceUrl) throw new Error('没有可用的视频链接')
      const response = await createJob(sourceUrl, {task_type: 'summary'})
      writeActive({jobId: response.job_id, url: sourceUrl})
      toast.success('已开始重新生成笔记')
      navigate(`/jobs/${response.job_id}`)
    } catch (err) {
      toast.error('重新生成失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setBusy(false)
      setMenuOpen(false)
    }
  }

  const remove = async () => {
    if (!doc?.id) return
    setBusy(true)
    try {
      await softDeleteDocument(doc.id)
      setRemoveOpen(false)
      toast.success('已从笔记中移除', '30 天内可在最近删除恢复', {
        durationMs: 5000,
        action: {
          label: '撤销',
          onClick: () => {
            void restoreDocument(doc.id).then(() => toast.success('已恢复笔记')).catch(() => toast.error('撤销失败'))
          },
        },
      })
      navigate(back.href)
    } catch (err) {
      toast.error('移除失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setBusy(false)
    }
  }

  const restore = async () => {
    if (!doc?.id) return
    setBusy(true)
    try {
      await restoreDocument(doc.id)
      toast.success('已恢复笔记')
      await load()
    } catch (err) {
      toast.error('恢复失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setBusy(false)
    }
  }

  const purge = async () => {
    if (!doc?.id || !bvid) return
    setBusy(true)
    try {
      await purgeDocument(doc.id, purgeInput.trim())
      setPurgeOpen(false)
      toast.success('已永久删除')
      navigate(from === 'trash' ? '/trash' : '/')
    } catch (err) {
      toast.error('删除失败', err instanceof Error ? err.message : '请重试')
    } finally {
      setBusy(false)
    }
  }

  const headings = useMemo(() => {
    if (chunks.length) {
      const seen = new Set<string>()
      return chunks.flatMap((chunk) => {
        const heading = chunk.heading_path.split(/[>··]/)[0]?.trim() || chunk.heading_path
        if (!heading || seen.has(heading)) return []
        seen.add(heading)
        return [{id: `chunk-${chunk.chunk_ord}`, text: heading, hit: q ? includesSearchQuery(chunk.text, q) || includesSearchQuery(heading, q) : false}]
      })
    }
    return markdown
      .split('\n')
      .map((line) => line.match(/^#{2,3}\s+(.+)/)?.[1]?.trim())
      .filter((text): text is string => Boolean(text) && text !== '笔记')
      .map((text, index) => ({id: `h-${index}`, text, hit: q ? includesSearchQuery(text, q) : false}))
  }, [chunks, markdown, q])

  if (loading) {
    return (
      <div>
        <BackButton href={back.href} label={back.label} />
        <PageLoading label="加载笔记…" />
      </div>
    )
  }
  if (error || (!content && !legacyJob)) {
    return (
      <div>
        <BackButton href={back.href} label={back.label} />
        <div className="mx-auto grid max-w-xl justify-items-center gap-3 py-16 text-center">
          <Rabbit mood="error" />
          <h1 className="text-lg font-semibold">这篇笔记不存在或已移除</h1>
          <p className="text-sm text-muted">{error}</p>
          <Button variant="secondary" onClick={() => navigate('/')}>
            返回全部笔记
          </Button>
        </div>
      </div>
    )
  }

  const title = doc?.title || legacyJob?.title || '未命名'
  const author = doc?.author || legacyJob?.author
  const mid = doc?.mid || legacyJob?.mid
  const tags = doc?.tags || legacyJob?.tags || []
  const duration = doc?.duration ?? legacyJob?.duration
  const play = biliPlayUrl(sourceUrl, bvid)

  return (
    <div>
      <div className="grid grid-cols-1 justify-center gap-0 lg:grid-cols-[minmax(0,720px)_220px] lg:gap-x-14">
        <article className="min-w-0">
          <BackButton href={back.href} label={back.label} />
          <h1 className="mt-3 font-serif text-[1.7rem] font-bold leading-snug tracking-[0.01em] break-words sm:text-[1.875rem]">
            {title}
          </h1>
          <div className="mt-2.5 flex flex-wrap items-center gap-x-3.5 gap-y-1 text-sm text-muted">
            {mid ? (
              <Link href={`/?up=${mid}`} className="hover:text-brand">
                {author || '未知 UP'}
              </Link>
            ) : (
              <span>{author || '未知 UP'}</span>
            )}
            <span>{formatDuration(duration)}</span>
            {play ? (
              <a href={play} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-brand">
                在 B 站打开 <ExternalLink size={13} />
              </a>
            ) : null}
          </div>
          {tags.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2.5">
              {tags.map((tag) => (
                <Link key={tag} href={`/?tag=${encodeURIComponent(tag)}`} className="text-[13px] text-muted hover:text-brand">
                  #{tag}
                </Link>
              ))}
            </div>
          ) : null}
          {deleted ? (
            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl bg-warning/15 px-3.5 py-2.5 text-sm">
              <span className="min-w-0 flex-1 basis-[240px]">
                这篇笔记在最近删除里{daysLeft != null ? `，${daysLeft} 天后永久删除` : ''}。恢复后会重新出现在笔记列表和搜索结果里。
              </span>
              <Button size="sm" variant="secondary" onClick={() => void restore()} disabled={busy}>
                恢复
              </Button>
            </div>
          ) : null}
          {legacy || missingFile ? (
            <p className="mt-4 rounded-xl bg-lift px-3.5 py-2.5 text-sm text-muted">
              {missingFile ? '笔记文件已丢失，可重新生成。' : '旧版 · 仅支持标题搜索。没有字幕全文索引。'}
            </p>
          ) : null}
          {stale ? (
            <p className="mt-3.5 rounded-xl bg-warning/15 px-3.5 py-2.5 text-sm">
              笔记在你搜索之后重新生成过，原来命中的段落已不存在。下面是当前版本。
            </p>
          ) : null}

          <div className="sticky top-14 z-10 mt-4 border-b border-line bg-canvas pb-2.5">
            <div className="flex flex-wrap items-center gap-2 pt-3">
              <Segmented
                value={tab}
                onChange={(next) => setParams({tab: next === 'notes' ? null : next})}
                options={[
                  {value: 'notes', label: '笔记'},
                  {value: 'subs', label: '字幕'},
                ]}
              />
              <span className="flex-1" />
              <Button size="sm" variant="secondary" onClick={() => void copyCurrent()}>
                <Copy size={14} />
                复制{tab === 'notes' ? '笔记' : '字幕'}
              </Button>
              <div className="relative">
                <Button
                  size="sm"
                  variant="ghost"
                  aria-haspopup="menu"
                  aria-label="更多操作"
                  className="px-2"
                  onClick={() => setMenuOpen((open) => !open)}
                >
                  <MoreHorizontal size={18} />
                </Button>
                {menuOpen ? (
                  <div
                    role="menu"
                    className="absolute right-0 top-11 z-30 min-w-[200px] rounded-[14px] border border-line bg-panel p-1.5 shadow-card"
                  >
                    <button
                      type="button"
                      className="block w-full rounded-[9px] px-3 py-2 text-left text-sm hover:bg-lift"
                      onClick={() => void regenerate()}
                    >
                      重新生成笔记
                      <span className="block text-xs text-muted">复用已保存的字幕，会产生模型费用</span>
                    </button>
                    {doc?.job_id || legacyJob?.id ? (
                      <Link
                        href={`/jobs/${doc?.job_id || legacyJob?.id}?from=doc`}
                        className="block rounded-[9px] px-3 py-2 text-sm hover:bg-lift"
                      >
                        处理记录
                      </Link>
                    ) : null}
                    <hr className="my-1.5 border-line" />
                    {deleted ? (
                      <button
                        type="button"
                        className="block w-full rounded-[9px] px-3 py-2 text-left text-sm text-danger hover:bg-lift"
                        onClick={() => {
                          setMenuOpen(false)
                          setPurgeOpen(true)
                        }}
                      >
                        永久删除
                        <span className="block text-xs text-muted">笔记、字幕和历史版本都会删除</span>
                      </button>
                    ) : doc?.id ? (
                      <button
                        type="button"
                        className="block w-full rounded-[9px] px-3 py-2 text-left text-sm text-danger hover:bg-lift"
                        onClick={() => {
                          setMenuOpen(false)
                          setRemoveOpen(true)
                        }}
                      >
                        从笔记中移除
                        <span className="block text-xs text-muted">30 天内可以在「最近删除」恢复</span>
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
            {q ? (
              <div className="mt-2.5 flex flex-wrap items-center gap-1 rounded-xl bg-brandSoft px-3.5 py-1.5 text-sm">
                <span className="min-w-0 flex-1 basis-[160px] break-words">本篇中的「{q}」</span>
                <span className="mr-1 tabular-nums text-muted">
                  {findTotal ? `${findIndex + 1}/${findTotal}` : '0/0'}
                </span>
                <Button size="sm" variant="ghost" className="px-2" aria-label="上一处" onClick={() => jumpFind(-1)}>
                  <ChevronLeft size={16} />
                </Button>
                <Button size="sm" variant="ghost" className="px-2" aria-label="下一处" onClick={() => jumpFind(1)}>
                  <ChevronRight size={16} />
                </Button>
              </div>
            ) : null}
          </div>

          {tab === 'notes' && headings.length > 0 ? (
            <details className="mt-3 rounded-xl border border-line bg-panel lg:hidden">
              <summary className="cursor-pointer px-3.5 py-2.5 text-sm text-muted">目录 · {headings.length} 节</summary>
              {headings.map((heading) => (
                <a key={heading.id} href={`#${heading.id}`} className="block border-t border-line px-3.5 py-2 text-sm">
                  {heading.text}
                </a>
              ))}
            </details>
          ) : null}

          <div className="mt-4">
            {tab === 'notes' ? (
              chunks.length > 0 ? (
                <div className={PROSE}>
                  {chunks.map((chunk) => (
                    <section
                      key={chunk.chunk_ord}
                      id={`chunk-${chunk.chunk_ord}`}
                      data-find-hit={q && includesSearchQuery(chunk.text, q) ? '' : undefined}
                      className="scroll-mt-48"
                    >
                      <MarkdownContent markdown={chunk.text} />
                    </section>
                  ))}
                </div>
              ) : markdown ? (
                <LazyMarkdown markdown={markdown} />
              ) : (
                <p className="py-10 text-center text-sm text-muted">没有笔记内容</p>
              )
            ) : cues.length > 0 ? (
              <ul>
                {cues.map((cue, index) => {
                  const hit =
                    String(index) === at ||
                    ((cue as {index?: number}).index != null && String((cue as {index?: number}).index) === at)
                  const secHit = at !== '' && Math.floor(cue.start) === Number(at)
                  const href = biliPlayUrl(sourceUrl, bvid, cue.start)
                  const matches = Boolean(q && includesSearchQuery(cue.text, q))
                  return (
                    <li
                      key={index}
                      id={`cue-${index}`}
                      data-sec={Math.floor(cue.start)}
                      data-find-hit={matches ? '' : undefined}
                      className={`grid scroll-mt-52 grid-cols-[3.5rem_minmax(0,1fr)] gap-3 rounded-lg px-2 py-1.5 ${
                        hit || secHit ? 'bg-brandSoft' : ''
                      }`}
                    >
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noreferrer"
                          title={`在 B 站播放 · ${formatClock(cue.start)}`}
                          className="pt-0.5 text-[13px] tabular-nums text-brand hover:underline"
                        >
                          {formatClock(cue.start)}
                        </a>
                      ) : (
                        <span className="pt-0.5 text-[13px] tabular-nums text-muted">{formatClock(cue.start)}</span>
                      )}
                      <span className="text-[15px] leading-7 break-words">
                        {q ? <SearchHighlight text={cue.text} query={q} mode="fts" /> : cue.text}
                        {href && (hit || secHit || matches) ? (
                          <a
                            href={href}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 block text-xs text-brand"
                          >
                            在 B 站播放 · {formatClock(cue.start)}
                          </a>
                        ) : null}
                      </span>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <div className="py-10 text-center">
                <h3 className="font-semibold">这篇笔记没有保存字幕</h3>
                <p className="mt-1 text-sm text-muted">早期版本生成的笔记只保留了正文。</p>
              </div>
            )}
          </div>
          <div className="mt-10 flex flex-wrap gap-x-4 gap-y-2 border-t border-line pt-4 text-[13px] text-muted">
            {bvid ? <span>{bvid}</span> : null}
            <span>字幕来源：{cues.length ? doc?.subtitle_source || '已保存' : '无'}</span>
            {mid ? (
              <Link href={`/?up=${mid}`} className="text-brand">
                {author} 的其他笔记
              </Link>
            ) : null}
          </div>
        </article>
        <aside className={`sticky top-32 hidden self-start pt-7 text-[13px] lg:block ${tab === 'notes' ? '' : 'invisible'}`}>
          <h4 className="mb-2 text-xs tracking-[0.06em] text-muted">目录</h4>
          {headings.map((heading) => (
            <a
              key={heading.id}
              href={`#${heading.id}`}
              className={`block border-l-2 border-line py-1 pl-3 text-muted hover:text-ink ${heading.hit ? 'after:ml-1.5 after:text-brand after:content-["•"]' : ''}`}
            >
              {heading.text}
            </a>
          ))}
        </aside>
      </div>

      <ConfirmDialog
        open={removeOpen}
        title="从笔记中移除？"
        description="会从列表和搜索里消失，30 天内可以在「最近删除」恢复。任务记录和 B 站视频不受影响。"
        confirmLabel="移除"
        danger
        loading={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoveOpen(false)}
      />
      <ConfirmDialog
        open={purgeOpen}
        title="永久删除这篇笔记？"
        description={
          <div className="grid gap-3">
            <p>笔记、字幕和历史版本都会删除，无法恢复。任务记录和 B 站视频不受影响。</p>
            <label className="grid gap-1 text-left text-[13px]">
              <span>
                输入 BV 号 <b className="font-mono text-ink">{bvid}</b> 确认
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
        loading={busy}
        confirmDisabled={!bvid || purgeInput.trim() !== bvid}
        onConfirm={() => void purge()}
        onCancel={() => {
          setPurgeOpen(false)
          setPurgeInput('')
        }}
      />
    </div>
  )
}
