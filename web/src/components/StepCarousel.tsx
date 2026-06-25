import {useEffect, useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {Check, ChevronLeft, ChevronRight, Circle, Loader2, RotateCcw, X} from 'lucide-react'

export type StepState = 'pending' | 'active' | 'done' | 'failed'

export interface StepDef {
  key: string
  label: string
  state: StepState
  render: () => ReactNode
}

interface StepCarouselProps {
  steps: StepDef[]
  /** index of the step that is currently progressing (the one to auto-track). */
  currentIndex: number
}

function StateIcon({state}: {state: StepState}) {
  if (state === 'done') return <Check size={14} />
  if (state === 'active') return <Loader2 size={14} className="animate-spin" />
  if (state === 'failed') return <X size={14} />
  return <Circle size={10} />
}

export function StepCarousel({steps, currentIndex}: StepCarouselProps) {
  const safeCurrent = Math.max(0, Math.min(steps.length - 1, currentIndex))
  const [displayIndex, setDisplayIndex] = useState(safeCurrent)
  const [manualLock, setManualLock] = useState(false)
  const lastCurrentRef = useRef(safeCurrent)

  // Auto-follow current when not manually locked.
  useEffect(() => {
    if (!manualLock) {
      setDisplayIndex(safeCurrent)
    }
    lastCurrentRef.current = safeCurrent
  }, [safeCurrent, manualLock])

  const go = (next: number) => {
    const clamped = Math.max(0, Math.min(steps.length - 1, next))
    setDisplayIndex(clamped)
    setManualLock(clamped !== safeCurrent)
  }

  return (
    <section className="min-w-0 w-full rounded-3xl bg-panel p-4 shadow-card sm:p-5">
      <div className="overflow-hidden">
        <div
          className="flex min-w-0 transition-transform duration-[220ms] ease-[cubic-bezier(0.2,0.8,0.2,1)]"
          style={{transform: `translateX(-${displayIndex * 100}%)`}}
        >
          {steps.map((step) => {
            const isFailed = step.state === 'failed'
            return (
              <div key={step.key} className="min-w-0 w-full shrink-0 pr-1">
                {/* h-full：让每个卡片填满 flex 行（align-items:stretch 已把各 slide 拉到
                    最高一张的高度），否则较矮的步骤边框只包到内容、各步骤高度看着不一致。 */}
                <div className={`grid h-full min-w-0 content-start gap-3 rounded-2xl border p-4 sm:p-5 ${
                  isFailed
                    ? 'border-danger/40 bg-danger/10'
                    : step.state === 'active'
                      ? 'border-brand/30 bg-brandSoft/40'
                      : 'border-line bg-lift'
                }`}>
                  <div className="flex items-center gap-3">
                    <span className={`grid h-7 w-7 place-items-center rounded-full ${
                      step.state === 'done'
                        ? 'bg-brand text-white'
                        : step.state === 'active'
                          ? 'bg-brand text-white'
                          : step.state === 'failed'
                            ? 'bg-danger text-white'
                            : 'bg-panel text-muted'
                    }`}>
                      <StateIcon state={step.state} />
                    </span>
                    <span className="text-base font-semibold text-ink">{step.label}</span>
                  </div>
                  <div className="min-w-0 min-h-[160px] max-h-[40vh] overflow-y-auto text-sm leading-6 text-muted">
                    {step.render()}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <button
          type="button"
          aria-label="上一步"
          onClick={() => go(displayIndex - 1)}
          disabled={displayIndex === 0}
          className="grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95 disabled:opacity-30"
        >
          <ChevronLeft size={18} />
        </button>

        <div className="flex items-center gap-2">
          {steps.map((step, idx) => {
            const isCurrent = idx === displayIndex
            return (
              <button
                key={step.key}
                type="button"
                aria-label={`第 ${idx + 1} 步：${step.label}`}
                aria-current={idx === safeCurrent ? 'step' : undefined}
                onClick={() => go(idx)}
                className={`h-2 rounded-full transition-all duration-[220ms] ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
                  isCurrent ? 'w-6 bg-brand' : step.state === 'done' ? 'w-2 bg-brand/40' : step.state === 'failed' ? 'w-2 bg-danger/60' : 'w-2 bg-line'
                }`}
              />
            )
          })}
        </div>

        <button
          type="button"
          aria-label="下一步"
          onClick={() => go(displayIndex + 1)}
          disabled={displayIndex === steps.length - 1}
          className="grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-lift active:scale-95 disabled:opacity-30"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {manualLock && (
        <div className="mt-3 flex justify-center">
          <button
            type="button"
            onClick={() => { setManualLock(false); setDisplayIndex(safeCurrent) }}
            className="inline-flex min-h-9 items-center gap-2 rounded-xl bg-lift px-3 text-xs text-muted transition hover:bg-line/70 active:scale-95"
          >
            <RotateCcw size={13} />
            跟随当前
          </button>
        </div>
      )}
    </section>
  )
}
