import {useCallback, useMemo} from 'react'
import {useLocation, useSearch} from 'wouter'
import {hrefWithQuery, parseQueryString, readUrlState, writeUrlState} from '../lib/urlState'

export function useUrlState() {
  const [pathname, navigate] = useLocation()
  const search = useSearch()
  const params = useMemo(() => parseQueryString(search), [search])
  const values = useMemo(() => readUrlState(search), [search])

  const setParams = useCallback(
    (patch: Record<string, string | null | undefined>, options?: {replace?: boolean}) => {
      const qs = writeUrlState(search, patch)
      navigate(qs ? `${pathname}?${qs}` : pathname, {replace: options?.replace ?? true})
    },
    [navigate, pathname, search],
  )

  const get = useCallback((key: string) => params.get(key) ?? '', [params])

  return {params, values, get, setParams, pathname, search, navigate, hrefWithQuery}
}
