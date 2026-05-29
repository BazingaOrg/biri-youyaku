// 支持的 B 站链接形态：
//   bilibili.com/video/(BV|av)…             桌面端
//   m.bilibili.com/video/(BV|av)…           移动端 web
//   b23.tv/<slug> / b.23.tv/<slug>          短链（含手机端 b.23.tv 变体）
//   bilibili.com/bangumi/play/…             番剧
//   BV…… / av……                              纯 ID
//
// 后置参数（?p、?t、?spm_id_from 等）一律忽略，交给后端 _parse_video_url。
const BILI_PATTERNS: RegExp[] = [
  /^https?:\/\/(www\.|m\.)?bilibili\.com\/video\/(BV[0-9A-Za-z]{10}|av[0-9]+)/i,
  /^https?:\/\/b\.?23\.tv\/[A-Za-z0-9]+/i,
  /^https?:\/\/(www\.|m\.)?bilibili\.com\/bangumi\/play\//i,
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

/**
 * 从用户粘贴的整段文本中抽出第一个 URL。手机端复制 B 站视频经常带上一整段
 * 「【标题】… https://b23.tv/xxx 复制本条…」，这里只取链接本体。
 * 若文本本身就是一个纯 BV/av ID，原样返回（trim 后）。
 */
export function extractBiliUrl(text: string): string {
  const match = text.match(/https?:\/\/[^\s）)\]]+/i)
  if (match) {
    return match[0]
  }
  return text.trim()
}
