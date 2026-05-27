const BILI_PATTERNS: RegExp[] = [
  /^https?:\/\/(www\.)?bilibili\.com\/video\/(BV[0-9A-Za-z]{10}|av[0-9]+)/i,
  /^https?:\/\/b23\.tv\/[A-Za-z0-9]+/i,
  /^https?:\/\/(www\.)?bilibili\.com\/bangumi\/play\//i,
  /^BV[0-9A-Za-z]{10}$/i,
  /^av[0-9]+$/i,
]

export function isValidBiliUrl(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) {
    return false
  }
  return BILI_PATTERNS.some((pattern) => pattern.test(trimmed))
}
