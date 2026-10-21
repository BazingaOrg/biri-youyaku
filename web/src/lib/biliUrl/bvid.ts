const BVID_RE = /BV[0-9A-Za-z]{10}/i

export function extractBvid(value: string): string | null {
  const match = value.match(BVID_RE)
  return match ? match[0] : null
}
