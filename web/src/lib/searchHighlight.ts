export type SearchHighlightMode = 'literal' | 'fts'

export interface SearchHighlightPart {
  text: string
  highlighted: boolean
}

const FTS_TOKEN_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[\p{L}\p{N}]+/gu
const FTS_SEPARATOR_PATTERN = '[\\p{P}\\p{S}\\s_]*'
const FTS_OPERATORS = new Set(['AND', 'OR', 'NOT', 'NEAR'])

function escapePattern(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightPatterns(query: string, mode: SearchHighlightMode) {
  const trimmed = query.trim()
  if (!trimmed) return []
  if (mode === 'literal') return [escapePattern(trimmed)]
  const groups = /\s/.test(trimmed) ? trimmed.split(/\s+/) : [trimmed]
  return groups.flatMap((group) => {
    const tokens = (group.match(FTS_TOKEN_PATTERN) ?? []).filter((token) => !FTS_OPERATORS.has(token))
    return tokens.length > 0 ? [tokens.map(escapePattern).join(FTS_SEPARATOR_PATTERN)] : []
  })
}

export function includesSearchQuery(text: string | null | undefined, query: string) {
  const needle = query.trim().toLocaleLowerCase()
  return Boolean(needle && (text ?? '').toLocaleLowerCase().includes(needle))
}

export function splitSearchHighlights(
  text: string,
  query: string,
  mode: SearchHighlightMode = 'literal',
): SearchHighlightPart[] {
  const patterns = highlightPatterns(query, mode)
  if (patterns.length === 0) return [{text, highlighted: false}]
  const splitPattern = new RegExp(`(${patterns.join('|')})`, 'giu')
  const matchPatterns = patterns.map((pattern) => new RegExp(`^(?:${pattern})$`, 'iu'))
  return text
    .split(splitPattern)
    .filter(Boolean)
    .map((part) => ({
      text: part,
      highlighted: matchPatterns.some((pattern) => pattern.test(part)),
    }))
}
