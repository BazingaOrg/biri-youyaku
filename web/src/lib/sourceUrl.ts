export type SourceProvider = 'bilibili' | 'youtube'

export interface RecognizedSource {
  provider: SourceProvider
  canonicalUrl: string
}

function parsedUrl(value: string): URL | null {
  try {
    const candidate = value.trim().match(/https?:\/\/[^\s]+/i)?.[0] ?? value.trim()
    const url = new URL(candidate.replace(/[)，、】【】》>]+$/u, ''))
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return null
    return url
  } catch {
    return null
  }
}

export function recognizeSourceUrl(value: string): RecognizedSource | null {
  const url = parsedUrl(value)
  if (!url) return null
  const host = url.hostname.toLowerCase().replace(/^www\./, '')
  if (host === 'bilibili.com' || host === 'm.bilibili.com' || host === 'b23.tv' || host === 'b.23.tv') {
    return {provider: 'bilibili', canonicalUrl: url.toString()}
  }
  const youtubeId =
    host === 'youtu.be'
      ? url.pathname.split('/').filter(Boolean)[0]
      : host === 'youtube.com' || host === 'm.youtube.com'
        ? url.searchParams.get('v') ?? (/^\/(?:shorts|embed)\/([^/?#]+)/.exec(url.pathname)?.[1] ?? null)
        : null
  if (youtubeId && /^[A-Za-z0-9_-]{11}$/.test(youtubeId)) {
    return {provider: 'youtube', canonicalUrl: `https://www.youtube.com/watch?v=${youtubeId}`}
  }
  return null
}

export function sourceLabel(provider?: string | null): string | null {
  if (provider === 'youtube') return 'YouTube'
  if (provider === 'bilibili') return 'B 站'
  if (provider === 'upload') return '导入'
  return null
}

export function sourceHref(value?: string | null): string | null {
  if (!value || value.startsWith('upload://') || value.startsWith('file:')) return null
  try {
    const url = new URL(value)
    if ((url.protocol !== 'https:' && url.protocol !== 'http:') || url.username || url.password) return null
    if (url.port && !((url.protocol === 'http:' && url.port === '80') || (url.protocol === 'https:' && url.port === '443'))) return null
    return url.toString()
  } catch {
    return null
  }
}

export function playbackUrl(sourceUrl?: string | null, provider?: string | null, startSec?: number | null) {
  if (!sourceUrl || sourceUrl.startsWith('upload://') || sourceUrl.startsWith('file:')) return null
  const source = recognizeSourceUrl(sourceUrl)
  if (!source) return null
  if (provider && source.provider !== provider) return null
  if (startSec == null || Number.isNaN(startSec)) return source.canonicalUrl
  const url = new URL(source.canonicalUrl)
  url.searchParams.set('t', String(Math.floor(startSec)))
  return url.toString()
}

export function subtitleLabel(source?: string | null): string {
  const labels: Record<string, string> = {platform: '平台字幕', automatic: '平台自动字幕', uploaded: '导入字幕', asr: '本地转写'}
  return labels[source || ''] || '已保存'
}
