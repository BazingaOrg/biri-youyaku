import {BILI_HOST_RE, TRAILING_PUNCT_RE} from './patterns'

/**
 * 从用户粘贴的整段文本中抽出第一个 B 站链接。
 *
 * 处理两种典型的「整段分享文本」：
 *   PC  ：「【标题】 https://www.bilibili.com/video/BV…/?share_source=…」
 *   手机：「【标题-哔哩哔哩】 https://b23.tv/xxx 复制本条信息…」
 *
 * 若没有显式协议头但本身就是 BV/av ID，原样返回（trim）。
 * 若文本里完全没有 https URL，把原文 trim 返回交给下游做友好提示。
 */
export function extractBiliUrl(text: string): string {
  if (!text) {
    return ''
  }
  const matches = text.match(/https?:\/\/[^\s）)\]】」』]+/gi) || []
  for (const raw of matches) {
    const cleaned = raw.replace(TRAILING_PUNCT_RE, '')
    try {
      const host = new URL(cleaned).host
      if (BILI_HOST_RE.test(host)) {
        return cleaned
      }
    } catch {
      // 非法 URL，跳过继续找下一个
    }
  }
  // 文本里没有 B 站域名链接，但可能是「随手贴了第一个 URL」—— 兜底返第一个，
  // 让 isValidBiliUrl 给用户一个明确的「不是 B 站链接」反馈。
  const first = matches[0]
  if (first !== undefined) {
    return first.replace(TRAILING_PUNCT_RE, '')
  }
  return text.trim()
}
