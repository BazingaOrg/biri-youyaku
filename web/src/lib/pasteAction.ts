export type PasteKind = 'text' | 'new-link' | 'existing' | 'trashed'
export type PastePrimary = 'generate' | 'read' | 'restore'

export interface PasteMatch {
  documentId: string
  title: string
  bvid?: string | null
  savedAt?: number | null
  daysLeft?: number | null
}

export interface PasteAction {
  kind: PasteKind
  primary: PastePrimary | null
  existing: PasteMatch | null
  trashed: PasteMatch | null
}

export function matchByBvid<T extends {bvid?: string | null}>(
  items: T[],
  bvid: string | null | undefined,
): T | null {
  if (!bvid) return null
  const needle = bvid.toLowerCase()
  return items.find((item) => (item.bvid || '').toLowerCase() === needle) ?? null
}

export function resolvePasteAction(input: {
  isLink: boolean
  existing?: PasteMatch | null
  trashed?: PasteMatch | null
}): PasteAction {
  if (!input.isLink) {
    return {kind: 'text', primary: null, existing: null, trashed: null}
  }
  if (input.trashed) {
    return {
      kind: 'trashed',
      primary: 'restore',
      existing: input.existing ?? null,
      trashed: input.trashed,
    }
  }
  if (input.existing) {
    return {kind: 'existing', primary: 'read', existing: input.existing, trashed: null}
  }
  return {kind: 'new-link', primary: 'generate', existing: null, trashed: null}
}
