import {ChevronDown, Mail, RotateCcw, Search} from 'lucide-react'
import {useState} from 'react'
import type React from 'react'
import {discoverLlmModels} from '../lib/api'
import type {ConfigDefaults, JobOptionOverrides, JobOptions} from '../lib/api'

interface OptionsFormProps {
  defaults: ConfigDefaults | null
  defaultsLoading: boolean
  options: JobOptionOverrides
  open: boolean
  onToggle: () => void
  onChange: (options: JobOptionOverrides) => void
}

type OptionKey = keyof JobOptions

function FieldShell({label, inherited, children, onReset}: {
  label: string
  inherited: boolean
  children: React.ReactNode
  onReset: () => void
}) {
  return (
    <div className="relative grid min-h-[98px] content-start gap-3 rounded-2xl bg-lift px-3 py-3">
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
      {!inherited && (
        <button type="button" aria-label={`恢复${label}默认值`} onClick={onReset} className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-md text-muted transition-transform active:scale-95">
          <RotateCcw size={13} />
        </button>
      )}
    </div>
  )
}

export function OptionsForm({defaults, defaultsLoading, options, open, onToggle, onChange}: OptionsFormProps) {
  const [modelOptions, setModelOptions] = useState<string[]>([])
  const [modelDiscoveryStatus, setModelDiscoveryStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [modelDiscoveryError, setModelDiscoveryError] = useState<string | null>(null)
  const patch = (partial: JobOptionOverrides) => onChange({...options, ...partial})
  const reset = (key: OptionKey) => {
    const next = {...options}
    delete next[key]
    onChange(next)
  }
  const isOverride = (key: OptionKey) => Object.prototype.hasOwnProperty.call(options, key)
  const value = <K extends OptionKey>(key: K): JobOptions[K] | '' => {
    const next = options[key] ?? defaults?.[key]
    return (next ?? '') as JobOptions[K] | ''
  }
  const discoverModels = async () => {
    setModelDiscoveryStatus('loading')
    setModelDiscoveryError(null)
    try {
      const response = await discoverLlmModels({
        llm_base_url: String(value('llm_base_url') || ''),
        llm_api_key: options.llm_api_key,
      })
      setModelOptions(response.models)
      setModelDiscoveryStatus('success')
      const currentModel = String(value('llm_model') || '')
      if (!currentModel || !response.models.includes(currentModel)) {
        patch({llm_model: response.models[0]})
      }
    } catch (err) {
      setModelDiscoveryStatus('error')
      setModelDiscoveryError(err instanceof Error ? err.message : '模型发现失败')
    }
  }

  return (
    <section className="mt-4 rounded-3xl bg-panel p-3 shadow-bili">
      <button
        type="button"
        className="flex min-h-10 w-full items-center justify-between rounded-2xl px-1 text-left transition-transform active:scale-95"
        onClick={onToggle}
      >
        <span className="font-medium">高级选项</span>
        <ChevronDown size={18} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="grid gap-3 pt-3 sm:grid-cols-3">
          {defaultsLoading && <p className="text-sm text-muted sm:col-span-3">正在读取服务器默认配置...</p>}
          {!defaultsLoading && defaults == null && <p className="text-sm text-danger sm:col-span-3">默认配置加载失败，提交时将使用后端默认值。</p>}

          <FieldShell label="邮件发送" inherited={!isOverride('email_enabled')} onReset={() => reset('email_enabled')}>
            <label className="flex min-h-11 items-center gap-3 rounded-xl bg-panel px-3">
              <input
                type="checkbox"
                checked={Boolean(value('email_enabled'))}
                onChange={(event) => patch({email_enabled: event.target.checked})}
                className="h-4 w-4 accent-pink"
              />
              <Mail size={16} className="text-pink" />
              <span className="text-sm font-medium">自动发邮件</span>
            </label>
          </FieldShell>

          <FieldShell label="LLM Base URL" inherited={!isOverride('llm_base_url')} onReset={() => reset('llm_base_url')}>
            <input
              value={value('llm_base_url')}
              onChange={(event) => patch({llm_base_url: event.target.value})}
              placeholder="https://api.openai.com/v1"
              className="min-h-11 w-full rounded-xl bg-panel px-3 pr-8 text-sm outline-none"
            />
          </FieldShell>

          <FieldShell label="LLM 模型" inherited={!isOverride('llm_model')} onReset={() => reset('llm_model')}>
            <div className="flex items-center gap-2">
              {modelOptions.length > 0 ? (
                <select
                  value={String(value('llm_model') || '')}
                  onChange={(event) => patch({llm_model: event.target.value})}
                  className="min-h-11 min-w-0 flex-1 rounded-xl bg-panel px-3 text-sm outline-none"
                >
                  {modelOptions.map((model) => <option key={model} value={model}>{model}</option>)}
                </select>
              ) : (
                <input
                  value={value('llm_model')}
                  onChange={(event) => patch({llm_model: event.target.value})}
                  placeholder="gpt-4o-mini"
                  className="min-h-11 min-w-0 flex-1 rounded-xl bg-panel px-3 pr-8 text-sm outline-none"
                />
              )}
              <button
                type="button"
                aria-label="发现模型"
                onClick={discoverModels}
                disabled={modelDiscoveryStatus === 'loading'}
                className="grid h-8 w-8 place-items-center rounded-md bg-panel text-muted transition-[transform,opacity] active:scale-95 disabled:opacity-50"
              >
                <Search size={14} />
              </button>
            </div>
            {modelDiscoveryStatus === 'success' && (
              <span className="text-xs text-muted">已发现 {modelOptions.length} 个模型</span>
            )}
            {modelDiscoveryError && (
              <span className="text-xs text-danger">{modelDiscoveryError}</span>
            )}
          </FieldShell>
        </div>
      )}
    </section>
  )
}
