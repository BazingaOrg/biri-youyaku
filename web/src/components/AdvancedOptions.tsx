import {useEffect, useState} from 'react'
import {ChevronDown, RotateCw, Search} from 'lucide-react'
import {discoverLlmModels, type JobOptionOverrides} from '../lib/api'
import {useToast} from './ToastProvider'

/**
 * 折叠的「高级选项」面板。默认收起；展开后让用户调整本次任务的：
 * - 总结语言（chip 切换，4 个常用预设）
 * - 强制 ASR（即便有官方字幕也走语音转写——字幕烂时用）
 * - LLM 模型（手填 + 一键拉模型列表）
 *
 * prompt_template 留给后续 A6（运行中换 prompt 重试）一起实现。
 */

const LANGUAGE_PRESETS = ['中文简体', '中文繁體', 'English', '日本語']

interface Props {
  value: Partial<JobOptionOverrides>
  onChange: (next: Partial<JobOptionOverrides>) => void
}

export function AdvancedOptions({value, onChange}: Props) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-2xl bg-lift">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-sm text-muted transition hover:text-ink"
        aria-expanded={open}
      >
        <span>高级选项</span>
        <ChevronDown
          size={16}
          className={`transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="grid gap-4 border-t border-line px-4 py-4">
          <LanguagePicker value={value.summary_language} onChange={(v) => onChange({...value, summary_language: v})} />
          <ForceAsrToggle value={value.force_asr ?? false} onChange={(v) => onChange({...value, force_asr: v})} />
          <ModelPicker value={value} onChange={onChange} />
        </div>
      )}
    </div>
  )
}

function LanguagePicker({value, onChange}: {value?: string; onChange: (v: string) => void}) {
  return (
    <div className="grid gap-2">
      <p className="text-xs font-medium text-muted">总结语言</p>
      <div className="flex flex-wrap gap-2">
        {LANGUAGE_PRESETS.map((preset) => {
          const active = value === preset
          return (
            <button
              key={preset}
              type="button"
              onClick={() => onChange(preset)}
              className={`rounded-full px-3 py-1 text-xs transition ${
                active
                  ? 'bg-brand text-white'
                  : 'bg-panel text-muted hover:text-ink'
              }`}
            >
              {preset}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ForceAsrToggle({value, onChange}: {value: boolean; onChange: (v: boolean) => void}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-2 text-sm text-ink">
      <span>
        <span className="font-medium">强制语音转写</span>
        <span className="ml-2 text-xs text-muted">忽略官方字幕，重新走 ASR</span>
      </span>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-[var(--color-brand)]"
      />
    </label>
  )
}

function ModelPicker({value, onChange}: Props) {
  const toast = useToast()
  const [discovering, setDiscovering] = useState(false)
  const [models, setModels] = useState<string[]>([])

  const discover = async () => {
    setDiscovering(true)
    try {
      const response = await discoverLlmModels({
        llm_base_url: value.llm_base_url,
        llm_api_key: value.llm_api_key,
      })
      setModels(response.models)
      toast.success(`找到 ${response.models.length} 个模型`)
    } catch (err) {
      toast.error('拉模型列表失败', err instanceof Error ? err.message : '')
    } finally {
      setDiscovering(false)
    }
  }

  return (
    <div className="grid gap-2">
      <p className="text-xs font-medium text-muted">LLM 模型</p>
      <div className="flex gap-2">
        <input
          type="text"
          list="llm-models-list"
          value={value.llm_model ?? ''}
          onChange={(e) => onChange({...value, llm_model: e.target.value || undefined})}
          placeholder="留空 = 用 .env 默认；可填 gpt-4o-mini / qwen-plus 等"
          className="min-h-10 flex-1 rounded-xl border border-line bg-panel px-3 text-sm outline-none transition-[border-color] focus:border-brand"
        />
        <button
          type="button"
          onClick={() => void discover()}
          disabled={discovering}
          aria-label="拉取可用模型列表"
          className="grid h-10 w-10 place-items-center rounded-xl bg-panel text-muted transition hover:text-brand disabled:opacity-50"
        >
          {discovering ? <RotateCw size={14} className="animate-spin" /> : <Search size={14} />}
        </button>
      </div>
      {models.length > 0 && (
        <datalist id="llm-models-list">
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      )}
    </div>
  )
}
