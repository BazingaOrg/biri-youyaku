import {useCallback, useEffect, useMemo, useState} from 'react'
import {useLocation} from 'wouter'
import {
  createJob,
  resolveSource,
  restoreDocument,
  type JobOptionOverrides,
} from '../lib/api'
import {resolvePasteAction, type PasteMatch} from '../lib/pasteAction'
import {recognizeSourceUrl} from '../lib/sourceUrl'
import {useRuntimeConfig} from './useRuntimeConfig'
import {writeActive} from '../lib/activeJob'
import {useToast} from '../components/ToastProvider'
import {hrefWithQuery} from '../lib/urlState'
import {docHref} from '../lib/docNav'

export function useOmniComposer(initialValue = '') {
  const [, navigate] = useLocation()
  const toast = useToast()
  const runtime = useRuntimeConfig()
  const [value, setValue] = useState(initialValue)
  const [busy, setBusy] = useState(false)
  const [existing, setExisting] = useState<PasteMatch | null>(null)
  const [trashed, setTrashed] = useState<PasteMatch | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [sourceState, setSourceState] = useState<'idle' | 'resolving' | 'error'>('idle')

  useEffect(() => {
    setValue(initialValue)
  }, [initialValue])

  const source = recognizeSourceUrl(value)
  const isLink = source != null

  useEffect(() => {
    if (!isLink) {
      setExisting(null)
      setTrashed(null)
      setActiveJobId(null)
      setSourceState('idle')
      return
    }
    let cancelled = false
    const controller = new AbortController()
    setExisting(null)
    setTrashed(null)
    setActiveJobId(null)
    setSourceState('resolving')
    const timer = window.setTimeout(() => void (async () => {
      try {
        const resolved = await resolveSource(source?.canonicalUrl ?? value, {signal: controller.signal})
        if (cancelled) return
        const trashHit = resolved.trashed ? {documentId: resolved.trashed.document_id, title: resolved.trashed.title, daysLeft: resolved.trashed.days_left} : null
        const liveHit = resolved.existing ? {documentId: resolved.existing.document_id, title: resolved.existing.title, savedAt: resolved.existing.saved_at} : null
        setTrashed(trashHit)
        setExisting(trashHit ? null : liveHit)
        setActiveJobId(resolved.active_job_id)
        setSourceState('idle')
      } catch {
        if (!cancelled) {
          setExisting(null)
          setTrashed(null)
          setActiveJobId(null)
          setSourceState('error')
        }
      }
    })(), 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [isLink, source?.canonicalUrl, value])

  const action = useMemo(
    () => resolvePasteAction({isLink, existing, trashed}),
    [existing, isLink, trashed],
  )

  const newSummaryOptions = useCallback((): Partial<JobOptionOverrides> => {
    const options: Partial<JobOptionOverrides> = {task_type: 'summary'}
    if (runtime?.email_configured) options.email_enabled = true
    return options
  }, [runtime?.email_configured])

  const generate = useCallback(async (force = false) => {
    const url = recognizeSourceUrl(value)?.canonicalUrl
    if (!url) {
      toast.error('目前支持 B 站和 YouTube 视频链接')
      return
    }
    if (activeJobId && !force) {
      navigate(`/jobs/${activeJobId}`)
      return
    }
    setBusy(true)
    try {
      const response = await createJob(url, newSummaryOptions(), {dedupe: force ? false : undefined})
      toast.success(response.deduped ? '这条视频已有笔记' : '已开始生成笔记', undefined, {
        dedupeKey: response.job_id,
      })
      if (response.deduped) {
        navigate(docHref(response.job_id))
        return
      }
      writeActive({jobId: response.job_id, url})
      navigate(`/jobs/${response.job_id}`)
    } catch (err) {
      toast.error('没能开始', err instanceof Error ? err.message : '换个链接试试')
    } finally {
      setBusy(false)
    }
  }, [activeJobId, navigate, newSummaryOptions, toast, value])

  const restore = useCallback(
    async (documentId: string) => {
      setBusy(true)
      try {
        await restoreDocument(documentId)
        toast.success('已恢复笔记')
        navigate(`/doc/${documentId}`)
      } catch (err) {
        toast.error('恢复失败', err instanceof Error ? err.message : '请重试')
      } finally {
        setBusy(false)
      }
    },
    [navigate, toast],
  )

  const submit = useCallback(async () => {
    const trimmed = value.trim()
    if (!trimmed) return
    if (action.kind === 'trashed' && action.trashed) {
      await restore(action.trashed.documentId)
      return
    }
    if (action.kind === 'existing' && action.existing) {
      navigate(`/doc/${action.existing.documentId}`)
      return
    }
    if (action.kind === 'new-link') {
      await generate()
      return
    }
    if (/^https?:\/\//i.test(trimmed)) {
      toast.error('这个链接暂不支持，可使用 B 站、YouTube 或导入文件')
      return
    }
    navigate(hrefWithQuery('/search', {q: trimmed, scope: 'all'}))
  }, [action, generate, navigate, restore, toast, value])

  return {value, setValue, action, busy, submit, generate, restore, isLink, activeJobId, sourceState}
}
