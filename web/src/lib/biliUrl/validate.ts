import {BILI_PATTERNS} from './patterns'
import {extractBiliUrl} from './extract'
import {normalizeBiliUrl} from './normalize'

/** 是否匹配任一支持的 B 站链接 / 纯 ID 形态。会先 normalize 一次。 */
export function isValidBiliUrl(value: string): boolean {
  const normalized = normalizeBiliUrl(value)
  if (!normalized) {
    return false
  }
  return BILI_PATTERNS.some((pattern) => pattern.test(normalized))
}

/** 从粘贴文本中提取并 normalize 出一个干净的 B 站链接，一次完成。 */
export function sanitizeBiliInput(text: string): string {
  return normalizeBiliUrl(extractBiliUrl(text))
}
