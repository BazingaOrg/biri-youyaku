// 跨文件共享的正则常量：host 判定 / 校验 pattern / query 白名单 / 末尾标点。
//
// 支持的 B 站链接形态：
//   bilibili.com/video/(BV|av)…             桌面端
//   m.bilibili.com/video/(BV|av)…           移动端 web
//   b23.tv/<slug> / b.23.tv/<slug>          短链
//   bilibili.com/bangumi/play/…             番剧
//   bilibili.com/list/...                   合集
//   bilibili.com/festival/...               活动页
//   BV…… / av……                              纯 ID
export const BILI_PATTERNS: RegExp[] = [
  /^https?:\/\/(www\.|m\.)?bilibili\.com\/video\/(BV[0-9A-Za-z]{10}|av[0-9]+)/i,
  /^https?:\/\/b\.?23\.tv\/[A-Za-z0-9]+/i,
  /^https?:\/\/(www\.|m\.)?bilibili\.com\/bangumi\/play\//i,
  /^https?:\/\/(www\.|m\.)?bilibili\.com\/(list|festival)\//i,
  /^BV[0-9A-Za-z]{10}$/i,
  /^av[0-9]+$/i,
]

// 仅与播放定位相关的参数保留（分 P 与起始时间），其它一律剥离。
export const KEEP_QUERY_KEYS = new Set(['p', 't', 'start_progress'])

export const BILI_HOST_RE = /(^|\.)bilibili\.com$|^b\.?23\.tv$/i

// URL 末尾常见的中英文标点 / 全半角括号 —— 截链接时一并去掉。
export const TRAILING_PUNCT_RE = /[。，、；：！？""''）)】」』,.;:!?]+$/u
