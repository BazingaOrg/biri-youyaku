import {useEffect, useRef, useState} from 'react'
import MindElixir from 'mind-elixir'
import type {MindElixirData, MindElixirInstance} from 'mind-elixir'
import 'mind-elixir/style'
import {FileImage, FileDown, Maximize2, Minimize2, ZoomIn, ZoomOut} from 'lucide-react'
import {summaryToMindmap} from '../../lib/markdown'
import {triggerDownload} from '../../lib/download'

const ZOOM_STEP = 0.15
const MIN_ZOOM = 0.4
const MAX_ZOOM = 1.8

/** 用 mind-elixir 把总结 markdown 渲染成只读思维导图，可导出 SVG/PNG。 */
export function MindmapView({markdown, title}: {markdown: string; title?: string}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const elRef = useRef<HTMLDivElement>(null)
  const meRef = useRef<MindElixirInstance | null>(null)
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [canFullscreen, setCanFullscreen] = useState(false)

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
      scaleMin: MIN_ZOOM,
      scaleMax: MAX_ZOOM,
    })
    me.init(summaryToMindmap(markdown, title || '总结') as unknown as MindElixirData)
    meRef.current = me
    setZoom(me.scaleVal)
    return () => {
      meRef.current = null
      el.innerHTML = ''
    }
  }, [markdown, title])

  useEffect(() => {
    setCanFullscreen(Boolean(document.fullscreenEnabled))
    const onFullscreenChange = () => {
      const active = document.fullscreenElement === panelRef.current
      setIsFullscreen(active)
      window.setTimeout(() => {
        meRef.current?.toCenter()
      }, 0)
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  const applyZoom = (next: number) => {
    const me = meRef.current
    if (!me) return
    const value = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next))
    me.scale(value)
    setZoom(me.scaleVal)
  }

  const zoomIn = () => applyZoom((meRef.current?.scaleVal ?? zoom) + ZOOM_STEP)
  const zoomOut = () => applyZoom((meRef.current?.scaleVal ?? zoom) - ZOOM_STEP)

  const toggleFullscreen = async () => {
    const panel = panelRef.current
    if (!panel || !document.fullscreenEnabled) return
    if (document.fullscreenElement === panel) {
      await document.exitFullscreen()
    } else {
      await panel.requestFullscreen()
    }
  }

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
    <div
      ref={panelRef}
      className={`grid gap-2 ${isFullscreen ? 'h-screen bg-panel p-3 sm:p-4' : ''}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 rounded-2xl bg-lift p-1">
          <button
            type="button"
            onClick={zoomOut}
            title="缩小"
            aria-label="缩小脑图"
            className="grid h-8 w-8 place-items-center rounded-xl text-muted transition hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-40"
            disabled={zoom <= MIN_ZOOM}
          >
            <ZoomOut size={15} />
          </button>
          <span className="min-w-12 text-center text-xs tabular-nums text-muted">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={zoomIn}
            title="放大"
            aria-label="放大脑图"
            className="grid h-8 w-8 place-items-center rounded-xl text-muted transition hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-40"
            disabled={zoom >= MAX_ZOOM}
          >
            <ZoomIn size={15} />
          </button>
          <button
            type="button"
            onClick={() => void toggleFullscreen()}
            title={isFullscreen ? '退出全屏' : '全屏查看'}
            aria-label={isFullscreen ? '退出全屏查看脑图' : '全屏查看脑图'}
            className="grid h-8 w-8 place-items-center rounded-xl text-muted transition hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-40"
            disabled={!canFullscreen}
          >
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
        </div>

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
      </div>
      <div
        ref={elRef}
        className={`w-full overflow-hidden bg-lift ${
          isFullscreen ? 'h-[calc(100vh-5rem)] rounded-xl' : 'h-[60vh] rounded-2xl'
        }`}
      />
    </div>
  )
}
