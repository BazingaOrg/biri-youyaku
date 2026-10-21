export type SearchScope = 'all' | 'notes' | 'subs'

export const SEARCH_SCOPES: SearchScope[] = ['all', 'notes', 'subs']

export function parseQueryString(search: string): URLSearchParams {
  const raw = search.startsWith('?') ? search.slice(1) : search
  return new URLSearchParams(raw)
}

export function readUrlState(search: string): Record<string, string> {
  const params = parseQueryString(search)
  const out: Record<string, string> = {}
  params.forEach((value, key) => {
    out[key] = value
  })
  return out
}

export function writeUrlState(
  search: string,
  patch: Record<string, string | null | undefined>,
): string {
  const next = parseQueryString(search)
  for (const [key, value] of Object.entries(patch)) {
    if (value == null || value === '') next.delete(key)
    else next.set(key, value)
  }
  return next.toString()
}

export function parseSearchScope(value: string | null | undefined): SearchScope {
  if (value === 'notes' || value === 'subs') return value
  return 'all'
}

export function hrefWithQuery(path: string, params: Record<string, string | null | undefined>) {
  const qs = writeUrlState('', params)
  return qs ? `${path}?${qs}` : path
}

export function viewStorageKey(path: string, search: string) {
  const qs = search.startsWith('?') ? search.slice(1) : search
  return qs ? `${path}?${qs}` : path
}
