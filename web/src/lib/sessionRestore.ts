import {viewStorageKey} from './urlState'

const PREFIX = 'biri.view.'

export interface ViewRestoreState {
  scrollY: number
  loadedPages: number
}

export function saveViewState(path: string, search: string, state: ViewRestoreState) {
  try {
    window.sessionStorage.setItem(
      PREFIX + viewStorageKey(path, search),
      JSON.stringify(state),
    )
  } catch {
    // sessionStorage is optional
  }
}

export function readViewState(path: string, search: string): ViewRestoreState | null {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + viewStorageKey(path, search))
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<ViewRestoreState>
    if (typeof value.scrollY !== 'number' || typeof value.loadedPages !== 'number') return null
    return {scrollY: value.scrollY, loadedPages: Math.max(1, value.loadedPages)}
  } catch {
    return null
  }
}
