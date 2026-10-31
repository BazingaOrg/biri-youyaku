import {useLocation, useSearch} from 'wouter'
import {useOmniComposer} from '../hooks/useOmniComposer'
import {OmniBar} from './OmniBar'
import {ImportPanel} from './ImportPanel'
import {useToast} from './ToastProvider'
import {writeActive} from '../lib/activeJob'
import {FileUp, X} from 'lucide-react'
import {useEffect, useRef, useState} from 'react'
import {Button} from './Button'
import {docHref} from '../lib/docNav'

export function BrowseOmni() {
  const [pathname, navigate] = useLocation()
  const toast = useToast()
  const params = new URLSearchParams(useSearch())
  const searching = pathname === '/search'
  const omni = useOmniComposer(searching ? params.get('q') ?? '' : params.get('paste') ?? '')
  const [importOpen, setImportOpen] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const importTriggerRef = useRef<HTMLButtonElement>(null)

  const closeImport = () => {
    if (importBusy) return
    setImportOpen(false)
    importTriggerRef.current?.focus()
  }

  useEffect(() => {
    if (!importOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || importBusy) return
      event.preventDefault()
      setImportOpen(false)
      importTriggerRef.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [importBusy, importOpen])

  if (pathname !== '/' && !searching) return null
  return (
    <div className="mx-auto w-full max-w-5xl">
      <OmniBar
        value={omni.value}
        onChange={omni.setValue}
        onClear={searching ? () => navigate('/') : undefined}
        onSubmit={() => void omni.submit()}
        action={omni.action}
        busy={omni.busy}
        sourceState={omni.sourceState}
        activeJobId={omni.activeJobId}
        hint={!searching}
        onGenerate={() => void omni.generate(true)}
        onRead={(id) => navigate(`/doc/${id}`)}
        onRestore={(id) => void omni.restore(id)}
        trailing={pathname === '/' ? (
          <Button
            ref={importTriggerRef}
            variant="ghost"
            size="sm"
            className="!min-h-10 shrink-0 px-2.5 text-muted hover:text-ink md:px-3"
            aria-label="导入文件：音视频或字幕"
            title="导入音视频或字幕"
            aria-expanded={importOpen}
            aria-controls="file-import-panel"
            disabled={importBusy}
            onClick={() => importOpen ? closeImport() : setImportOpen(true)}
          >
            <FileUp size={16} />
            <span className="hidden md:inline">导入文件</span>
          </Button>
        ) : undefined}
      />
      {pathname === '/' && importOpen ? (
        <div id="file-import-panel" className="relative mt-3 animate-fade-in-up">
          <ImportPanel onBusyChange={setImportBusy} onAccepted={(jobId, deduped) => {
            setImportBusy(false)
            setImportOpen(false)
            writeActive({jobId, url: 'upload://local'})
            toast.success(deduped ? '这份内容已有笔记' : '已交给后台生成笔记', undefined, {dedupeKey: jobId})
            navigate(deduped ? docHref(jobId, {from: 'task'}) : `/jobs/${jobId}`)
          }} />
          <button type="button" aria-label="收起导入文件" disabled={importBusy} onClick={closeImport} className="absolute right-2 top-2 grid h-10 w-10 place-items-center rounded-[10px] text-muted hover:bg-lift hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"><X size={16} /></button>
        </div>
      ) : null}
    </div>
  )
}
