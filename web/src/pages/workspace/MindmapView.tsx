import {useEffect, useRef} from 'react'
import MindElixir from 'mind-elixir'
import type {MindElixirData, MindElixirInstance} from 'mind-elixir'
import 'mind-elixir/style'
import {FileImage, FileDown} from 'lucide-react'
import {summaryToMindmap} from '../../lib/markdown'
import {triggerDownload} from '../../lib/download'

/** 用 mind-elixir 把总结 markdown 渲染成只读思维导图，可导出 SVG/PNG。 */
export function MindmapView({markdown, title}: {markdown: string; title?: string}) {
  const elRef = useRef<HTMLDivElement>(null)
  const meRef = useRef<MindElixirInstance | null>(null)

  useEffect(() => {
    const el = elRef.current
    if (!el) return
    const me = new MindElixir({
      el,
      direction: MindElixir.SIDE,
      editable: false,
      contextMenu: false,
      toolBar: false,
      keypress: false,
    })
    me.init(summaryToMindmap(markdown, title || '总结') as unknown as MindElixirData)
    meRef.current = me
    return () => {
      meRef.current = null
      el.innerHTML = ''
    }
  }, [markdown, title])

  const fileBase = (title || 'mindmap').replace(/[\\/:*?"<>|]+/g, '_')
  const exportSvg = () => {
    const blob = meRef.current?.exportSvg()
    if (blob) triggerDownload(blob, `${fileBase}.svg`)
  }
  const exportPng = async () => {
    const blob = await meRef.current?.exportPng()
    if (blob) triggerDownload(blob, `${fileBase}.png`)
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={exportSvg}
          className="inline-flex items-center gap-1 rounded-xl bg-lift px-3 py-1.5 text-xs text-muted transition hover:bg-line/70 hover:text-ink active:scale-95"
        >
          <FileDown size={14} /> SVG
        </button>
        <button
          type="button"
          onClick={() => void exportPng()}
          className="inline-flex items-center gap-1 rounded-xl bg-lift px-3 py-1.5 text-xs text-muted transition hover:bg-line/70 hover:text-ink active:scale-95"
        >
          <FileImage size={14} /> PNG
        </button>
      </div>
      <div ref={elRef} className="h-[60vh] w-full overflow-hidden rounded-2xl bg-lift" />
    </div>
  )
}
