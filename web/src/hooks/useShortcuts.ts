import {useEffect} from 'react'

interface ShortcutHandlers {
  onPaste?: () => void
  onSubmit?: () => void
  onCancel?: () => void
  onFocusSearch?: () => void
  onHelp?: () => void
}

function isEditable(target: EventTarget | null) {
  const element = target as HTMLElement | null
  if (!element) {
    return false
  }
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName) || element.isContentEditable
}

export function useShortcuts(handlers: ShortcutHandlers) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey
      if (event.key === '?' && !isEditable(event.target)) {
        event.preventDefault()
        handlers.onHelp?.()
        return
      }
      if (mod && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        handlers.onFocusSearch?.()
        return
      }
      if (mod && event.key === 'Enter') {
        event.preventDefault()
        handlers.onSubmit?.()
        return
      }
      if (mod && event.key === '.') {
        event.preventDefault()
        handlers.onCancel?.()
        return
      }
      if (mod && event.key.toLowerCase() === 'v' && !isEditable(event.target)) {
        event.preventDefault()
        handlers.onPaste?.()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [handlers])
}
