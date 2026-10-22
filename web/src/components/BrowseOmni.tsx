import {useLocation, useSearch} from 'wouter'
import {useOmniComposer} from '../hooks/useOmniComposer'
import {OmniBar} from './OmniBar'

export function BrowseOmni() {
  const [pathname, navigate] = useLocation()
  const params = new URLSearchParams(useSearch())
  const searching = pathname === '/search'
  const omni = useOmniComposer(searching ? params.get('q') ?? '' : params.get('paste') ?? '')
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
        hint={!searching}
        onGenerate={() => void omni.generate()}
        onRead={(id) => navigate(`/doc/${id}`)}
        onRestore={(id) => void omni.restore(id)}
      />
    </div>
  )
}
