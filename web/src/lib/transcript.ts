import type {Job} from './api'

type TranscriptItem = Job['transcript'][number]

function parseTime(value: string) {
  const normalized = value.trim().replace(',', '.')
  const parts = normalized.split(':').map(Number)
  if (parts.some(Number.isNaN)) {
    return 0
  }
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2]
  }
  if (parts.length === 2) {
    return parts[0] * 60 + parts[1]
  }
  return Number(normalized) || 0
}

export function parseTranscriptFile(text: string): TranscriptItem[] {
  const blocks = text.replace(/\r/g, '').split(/\n{2,}/)
  const timedItems: TranscriptItem[] = []
  for (const block of blocks) {
    const lines = block.split('\n').map((line) => line.trim()).filter(Boolean)
    const timeIndex = lines.findIndex((line) => line.includes('-->'))
    if (timeIndex < 0) {
      continue
    }
    const [startText, endText] = lines[timeIndex].split('-->').map((part) => part.trim().split(/\s+/)[0])
    const body = lines.slice(timeIndex + 1).join(' ').trim()
    if (body) {
      timedItems.push({start: parseTime(startText), end: parseTime(endText), text: body})
    }
  }
  if (timedItems.length > 0) {
    return timedItems
  }
  return text
    .split(/\r?\n/)
    .map((line, index) => ({start: index, end: index, text: line.trim()}))
    .filter((item) => item.text)
}
