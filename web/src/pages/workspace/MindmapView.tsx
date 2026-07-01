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
    if (!isFullscreen) {
      window.setTimeout(() => meRef.current?.toCenter(), 0)
      return
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const recenter = () => {
      window.setTimeout(() => meRef.current?.toCenter(), 0)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsFullscreen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('resize', recenter)
    window.addEventListener('orientationchange', recenter)
    recenter()
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('resize', recenter)
      window.removeEventListener('orientationchange', recenter)
    }
  }, [isFullscreen])

  const applyZoom = (next: number) => {
    const me = meRef.current
    if (!me) return
    const value = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next))
    me.scale(value)
    setZoom(me.scaleVal)
  }

  const zoomIn = () => applyZoom((meRef.current?.scaleVal ?? zoom) + ZOOM_STEP)
  const zoomOut = () => applyZoom((meRef.current?.scaleVal ?? zoom) - ZOOM_STEP)

  const toggleFullscreen = () => {
    setIsFullscreen((value) => !value)
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
      style={
        isFullscreen
          ? {
              paddingTop: 'max(0.75rem, env(safe-area-inset-top))',
              paddingRight: 'max(0.75rem, env(safe-area-inset-right))',
              paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))',
              paddingLeft: 'max(0.75rem, env(safe-area-inset-left))',
            }
          : undefined
      }
      className={`grid gap-2 ${
        isFullscreen ? 'fixed inset-0 z-50 grid-rows-[auto_minmax(0,1fr)] overscroll-contain bg-panel' : ''
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 rounded-2xl bg-lift p-1">
          <button
            type="button"
            onClick={zoomOut}
            title="缩小"
            aria-label="缩小脑图"
            className="grid h-10 w-10 place-items-center rounded-xl text-muted transition hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-40"
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
            className="grid h-10 w-10 place-items-center rounded-xl text-muted transition hover:bg-line/70 hover:text-ink active:scale-95 disabled:opacity-40"
            disabled={zoom >= MAX_ZOOM}
          >
            <ZoomIn size={15} />
          </button>
          <button
            type="button"
            onClick={toggleFullscreen}
            title={isFullscreen ? '退出全屏' : '全屏查看'}
            aria-label={isFullscreen ? '退出全屏查看脑图' : '全屏查看脑图'}
            className="grid h-10 w-10 place-items-center rounded-xl text-muted transition hover:bg-line/70 hover:text-ink active:scale-95"
          >
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={exportSvg}
            className="inline-flex min-h-10 items-center gap-1 rounded-xl bg-lift px-3 text-xs text-muted transition hover:bg-line/70 hover:text-ink active:scale-95"
          >
            <FileDown size={14} /> SVG
          </button>
          <button
            type="button"
            onClick={() => void exportPng()}
            className="inline-flex min-h-10 items-center gap-1 rounded-xl bg-lift px-3 text-xs text-muted transition hover:bg-line/70 hover:text-ink active:scale-95"
          >
            <FileImage size={14} /> PNG
          </button>
        </div>
      </div>
      <div
        ref={elRef}
        className={`w-full overflow-hidden bg-lift ${
          isFullscreen ? 'h-full min-h-0 rounded-xl' : 'h-[60vh] rounded-2xl'
        }`}
      />
    </div>
  )
}
