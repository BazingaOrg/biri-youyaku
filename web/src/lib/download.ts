/**
 * 触发浏览器下载一个 Blob。
 *
 * 关键点：`revokeObjectURL` 必须延后，不能在 `click()` 之后同步调用——部分浏览器
 * （尤其 Safari）此时还没真正开始读取 blob，立刻 revoke 会让下载直接失败/为空。
 */
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // 给浏览器一帧时间把下载排进队列，再回收 URL。
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
