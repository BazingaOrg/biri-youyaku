import {BILI_HOST_RE, KEEP_QUERY_KEYS} from './patterns'

/**
 * 去掉 B 站分享链接里的追踪参数。保留分 P (`p`) 与起始时间 (`t` / `start_progress`)。
 *
 * - PC 「复制视频地址」会挂 `share_source=copy_web&vd_source=…`
 * - 手机端 webview 经常挂 `spm_id_from / from_source / from_spmid / msource / refer_from / unique_k / buvid / mid / ts / bbid` 等
 *
 * 这些参数对解析没有意义，反而会污染日志与 dedup hash。
 */
export function normalizeBiliUrl(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) {
    return trimmed
  }
  // 非 URL（裸 BV/av ID）直接返回。
  if (!/^https?:\/\//i.test(trimmed)) {
    return trimmed
  }
  let parsed: URL
  try {
    parsed = new URL(trimmed)
  } catch {
    return trimmed
  }
  // 仅对 B 站域名生效，避免误伤其它 URL。
  if (!BILI_HOST_RE.test(parsed.host)) {
    return trimmed
  }
  const kept: Array<[string, string]> = []
  parsed.searchParams.forEach((v, k) => {
    if (KEEP_QUERY_KEYS.has(k.toLowerCase())) {
      kept.push([k, v])
    }
  })
  parsed.search = ''
  for (const [k, v] of kept) {
    parsed.searchParams.append(k, v)
  }
  parsed.hash = ''
  return parsed.toString()
}
