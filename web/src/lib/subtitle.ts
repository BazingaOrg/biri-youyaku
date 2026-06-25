import type {Job} from './api'

type Cue = Job['transcript'][number] // {start, end, text}

function pad(value: number, width = 2): string {
  return String(Math.max(0, Math.floor(value))).padStart(width, '0')
}

/** 秒 → SRT 时间戳 `HH:MM:SS,mmm`。 */
export function formatSrtTimestamp(seconds: number): string {
  const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : 0
  const ms = Math.round((safe - Math.floor(safe)) * 1000)
  const total = Math.floor(safe)
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)},${pad(ms, 3)}`
}

/**
 * transcript → SRT 字幕文本。
 *
 * 选 SRT(.srt) 的理由：它是最通用的字幕格式（几乎所有播放器都认），块状排版
 * （序号 / 时间轴 / 文本 / 空行）天然方便阅读；相比纯 .txt 它是真正的字幕文件，
 * 相比 .vtt 兼容面更广。
 */
export function transcriptToSrt(items: Cue[]): string {
  const blocks: string[] = []
  items.forEach((item, index) => {
    const text = (item.text ?? '').trim().replace(/\s+/g, ' ')
    if (!text) return
    const start = Number(item.start) || 0
    // 兜底结束时间：缺失 / 不晚于开始时，用下一条的开始时间，再兜底 +2s，
    // 避免出现 0 时长或倒挂的 cue（部分平台字幕 / ASR 不带 end）。
    let end = Number(item.end) || 0
    if (end <= start) {
      const next = items[index + 1]
      const nextStart = next ? Number(next.start) || 0 : 0
      end = nextStart > start ? nextStart : start + 2
    }
    // 序号用 blocks.length+1：跳过的空行不会在编号里留空洞。
    blocks.push(`${blocks.length + 1}\n${formatSrtTimestamp(start)} --> ${formatSrtTimestamp(end)}\n${text}`)
  })
  return blocks.length > 0 ? `${blocks.join('\n\n')}\n` : ''
}
