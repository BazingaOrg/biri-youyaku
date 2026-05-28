import {useState} from 'react'
import {KeyRound, X} from 'lucide-react'
import {getApiToken, setApiToken} from '../lib/api'

const dismissedKey = 'biri-youyaku-token-dialog-dismissed'

export function ApiTokenDialog() {
  const [open, setOpen] = useState(() => !getApiToken() && window.localStorage.getItem(dismissedKey) !== '1')
  const [token, setToken] = useState('')

  if (!open) {
    return null
  }

  const close = () => {
    window.localStorage.setItem(dismissedKey, '1')
    setOpen(false)
  }

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-ink/30 p-4 backdrop-blur-sm">
      <div className="animate-pop relative w-full max-w-[420px] rounded-3xl bg-panel p-6 shadow-card">
        <button type="button" aria-label="关闭授权框" onClick={close} className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95">
          <X size={17} />
        </button>
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brandSoft text-brand">
          <KeyRound size={22} />
        </span>
        <h2 className="mt-4 text-lg font-semibold">输入 API Token</h2>
        <p className="mt-2 text-sm leading-6 text-muted">Token 只保存在当前浏览器的 localStorage，不会打进前端 bundle。</p>
        <input value={token} onChange={(event) => setToken(event.target.value)} placeholder="Bearer token" className="mt-4 min-h-11 w-full rounded-2xl border border-line bg-lift px-3 text-sm outline-none focus:border-brand" />
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={close} className="min-h-11 rounded-2xl px-4 text-sm font-medium text-muted transition hover:bg-lift active:scale-95">暂不填写</button>
          <button type="button" onClick={() => { setApiToken(token); setOpen(false); window.location.reload() }} disabled={!token.trim()} className="min-h-11 rounded-2xl bg-brand px-4 text-sm font-semibold text-white transition active:scale-95 disabled:opacity-50">保存</button>
        </div>
      </div>
    </div>
  )
}
