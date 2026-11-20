import {catalogQuery, hrefWithQuery} from './urlState'

export type DocFrom = 'search' | 'catalog' | 'up' | 'tag' | 'task' | 'trash' | 'library'

export interface BackTarget {
  label: string
  href: string
}

export function readDocFrom(value: string | null | undefined): DocFrom | null {
  if (value === 'search' || value === 'catalog' || value === 'up' || value === 'tag' || value === 'task' || value === 'trash' || value === 'library') {
    return value
  }
  return null
}

export function backTarget(params: {
  from?: string | null
  q?: string | null
  scope?: string | null
  up?: string | null
  filter?: string | null
  order?: string | null
  tag?: string | null
  author?: string | null
}): BackTarget {
  const from = readDocFrom(params.from)
  if (from === 'search') {
    const q = params.q?.trim() || ''
    return {
      label: q ? `搜索「${q}」` : '搜索',
      href: hrefWithQuery('/search', {q: q || null, scope: params.scope || 'all'}),
    }
  }
  if (from === 'catalog' && params.up && /^\d+$/.test(params.up)) {
    const path = `/up/${params.up}`
    const search = catalogQuery(params.q ?? '', params.filter ?? '', params.order ?? '')
    return {label: '返回投稿列表', href: search ? `${path}?${search}` : path}
  }
  if (from === 'up') {
    const author = params.author?.trim()
    return {
      label: author ? `${author} 的笔记` : '该 UP 的笔记',
      href: hrefWithQuery('/', {up: params.up || null}),
    }
  }
  if (from === 'tag') {
    const tag = params.tag?.trim() || ''
    return {label: tag ? `#${tag}` : '标签', href: hrefWithQuery('/', {tag: tag || null})}
  }
  if (from === 'task') return {label: '任务', href: '/tasks'}
  if (from === 'trash') return {label: '最近删除', href: '/trash'}
  return {label: '全部笔记', href: '/'}
}

export function docHref(
  id: string,
  extra: Record<string, string | null | undefined> = {},
) {
  return hrefWithQuery(`/doc/${id}`, extra)
}

export function libraryItemHref(
  item: {document_id?: string | null; job_id?: string | null; id: string},
  extra: Record<string, string | null | undefined> = {},
) {
  const id = item.document_id || item.id || item.job_id
  if (!id) return '/'
  return docHref(id, extra)
}

export function processingRecordHref(jobId: string, readerHref: string) {
  return hrefWithQuery(`/jobs/${encodeURIComponent(jobId)}`, {from: 'doc', reader: readerHref})
}

export function readerReturnHref(search: string): string | null {
  const params = new URLSearchParams(search)
  const reader = params.get('reader')
  if (params.get('from') !== 'doc' || !reader?.startsWith('/doc/')) return null
  const target = new URL(reader, window.location.origin)
  return /^\/doc\/[^/]+$/.test(target.pathname) ? target.pathname + target.search + target.hash : null
}
