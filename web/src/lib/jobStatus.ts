import type {JobStatus} from './api'

/**
 * 按 pipeline 时序给 status 排序。同 ordinal 的（COMPLETED/FAILED/CANCELED 都是终态 7）
 * 视为「终态」，互相不分先后；任何运行中状态都比终态小。
 *
 * 用途：refresh() 拿到的 snapshot 跟 SSE 推送的 patch 之间存在乱序窗口。
 * 当 current.status 比 incoming.status 「更靠后」时，应该保留 current 的状态，
 * 避免把已经收到的「更新」打回老状态。
 */
export const STATUS_ORDER: Record<JobStatus, number> = {
  PENDING: 0,
  FETCHING_META: 1,
  DOWNLOADING_AUDIO: 2,
  TRANSCRIBING: 3,
  TRANSCRIPT_READY: 4,
  SUMMARIZING: 5,
  EMAILING: 6,
  COMPLETED: 7,
  FAILED: 7,
  CANCELED: 7,
}

/** current 是否比 incoming 更靠后（更新）。相等返回 false（让 refresh 正常覆盖）。 */
export function isStatusNewer(current: JobStatus, incoming: JobStatus): boolean {
  return STATUS_ORDER[current] > STATUS_ORDER[incoming]
}
