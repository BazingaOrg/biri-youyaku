import {useCallback, useEffect, useMemo, useState} from 'react'
import {useLocation} from 'wouter'
import {
  createJob,
  listLibrary,
  listLibraryTrash,
  restoreDocument,
  searchLibrary,
  type JobOptionOverrides,
} from '../lib/api'
import {extractBvid, isValidBiliUrl, sanitizeBiliInput} from '../lib/biliUrl'
import {matchByBvid, resolvePasteAction, type PasteMatch} from '../lib/pasteAction'
import {useRuntimeConfig} from './useRuntimeConfig'
import {writeActive} from '../lib/activeJob'
import {useToast} from '../components/ToastProvider'
import {hrefWithQuery} from '../lib/urlState'

export function useOmniComposer(initialValue = '') {
  const [, navigate] = useLocation()
  const toast = useToast()
  const runtime = useRuntimeConfig()
  const [value, setValue] = useState(initialValue)
  const [busy, setBusy] = useState(false)
  const [existing, setExisting] = useState<PasteMatch | null>(null)
  const [trashed, setTrashed] = useState<PasteMatch | null>(null)

  useEffect(() => {
    setValue(initialValue)
  }, [initialValue])

  const cleaned = sanitizeBiliInput(value)
  const isLink = isValidBiliUrl(cleaned)
  const bvid = extractBvid(cleaned) || extractBvid(value)

  useEffect(() => {
    if (!isLink) {
      setExisting(null)
      setTrashed(null)
      return
    }
    let cancelled = false
    const controller = new AbortController()
    void (async () => {
      try {
        const [trash, library, search] = await Promise.all([
          listLibraryTrash({signal: controller.signal}),
          listLibrary({limit: 40}, {signal: controller.signal}),
          bvid
            ? searchLibrary({q: bvid, scope: 'all', limit: 8}, {signal: controller.signal}).catch(() => null)
            : Promise.resolve(null),
        ])
        if (cancelled) return
        const trashHit = matchByBvid(
          trash.items.map((item) => ({
            bvid: item.bvid,
            documentId: item.document_id,
            title: item.title || '未命名',
            daysLeft: item.days_left,
          })),
          bvid,
        )
        const liveItems: PasteMatch[] = [
          ...library.items.map((item) => ({
            documentId: item.document_id || item.id,
            title: item.title,
            bvid: item.bvid,
            savedAt: item.saved_at,
          })),
          ...(search?.groups ?? []).map((group) => ({
            documentId: group.document_id || group.job_id || '',
            title: group.title,
            bvid: group.bvid,
            savedAt: group.saved_at,
          })),
        ].filter((item) => item.documentId)
        const liveHit = matchByBvid(liveItems, bvid)
        setTrashed(trashHit)
        setExisting(trashHit ? null : liveHit)
      } catch {
        if (!cancelled) {
          setExisting(null)
          setTrashed(null)
        }
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [bvid, isLink])

  const action = useMemo(
    () => resolvePasteAction({isLink, existing, trashed}),
    [existing, isLink, trashed],
  )

  const newSummaryOptions = useCallback((): Partial<JobOptionOverrides> => {
    const options: Partial<JobOptionOverrides> = {task_type: 'summary'}
    if (runtime?.email_configured) options.email_enabled = true
    return options
  }, [runtime?.email_configured])

  const generate = useCallback(async () => {
    const url = sanitizeBiliInput(value)
    if (!isValidBiliUrl(url)) {
      toast.error('请输入有效的 B 站视频链接')
      return
    }
    setBusy(true)
    try {
      const response = await createJob(url, newSummaryOptions())
      writeActive({jobId: response.job_id, url})
      toast.success(response.deduped ? '这条视频已有笔记' : '已开始生成笔记', undefined, {
        dedupeKey: response.job_id,
      })
      navigate(`/jobs/${response.job_id}`)
    } catch (err) {
      toast.error('没能开始', err instanceof Error ? err.message : '换个链接试试')
    } finally {
      setBusy(false)
    }
  }, [navigate, newSummaryOptions, toast, value])

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
    navigate(hrefWithQuery('/search', {q: trimmed, scope: 'all'}))
  }, [action, generate, navigate, restore, value])

  return {value, setValue, action, busy, submit, generate, restore, isLink}
}
