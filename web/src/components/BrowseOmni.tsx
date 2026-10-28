import {useLocation, useSearch} from 'wouter'
import {useOmniComposer} from '../hooks/useOmniComposer'
import {OmniBar} from './OmniBar'
import {ImportPanel} from './ImportPanel'
import {useToast} from './ToastProvider'
import {writeActive} from '../lib/activeJob'
import {FileUp, X} from 'lucide-react'
import {useState} from 'react'
import {Button} from './Button'

export function BrowseOmni() {
  const [pathname, navigate] = useLocation()
  const toast = useToast()
  const params = new URLSearchParams(useSearch())
  const searching = pathname === '/search'
  const omni = useOmniComposer(searching ? params.get('q') ?? '' : params.get('paste') ?? '')
  const [importOpen, setImportOpen] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
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
      />
      {pathname === '/' ? (
        <div className="mt-3">
          {!importOpen ? <Button variant="secondary" aria-expanded={false} aria-controls="file-import-panel" onClick={() => setImportOpen(true)}><FileUp size={16} />导入文件</Button> : null}
          {importOpen ? <div id="file-import-panel" className="relative"><ImportPanel onBusyChange={setImportBusy} onAccepted={(jobId, deduped) => {
            writeActive({jobId, url: 'upload://local'})
            toast.success(deduped ? '这份内容已有笔记' : '已交给后台生成笔记', undefined, {dedupeKey: jobId})
            navigate(`/jobs/${jobId}`)
          }} /><button type="button" aria-label="收起导入文件" aria-expanded="true" disabled={importBusy} onClick={() => setImportOpen(false)} className="absolute right-3 top-3 grid h-8 w-8 place-items-center rounded-[10px] text-muted hover:bg-lift hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"><X size={16} /></button></div> : null}
        </div>
      ) : null}
    </div>
  )
}
