import type {JobCreationResult} from './api'

export function createdNoteId(result: JobCreationResult) {
  return result.deduped && result.status === 'COMPLETED' ? result.read_id || null : null
}

export function creationMessage(result: JobCreationResult) {
  if (createdNoteId(result)) return '这份内容已有笔记'
  return result.deduped ? '已复用原任务' : '已开始生成笔记'
}
