import {Component} from 'react'
import type {ErrorInfo, ReactNode} from 'react'
import {RotateCw} from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * Top-level error boundary that catches render crashes from ReactMarkdown,
 * mind-elixir, or any descendant component and shows a friendly fallback
 * instead of a blank white page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = {error: null}

  static getDerivedStateFromError(error: Error): State {
    return {error}
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="grid min-h-[60vh] place-items-center gap-4 px-4 text-center">
          <div>
            <p className="text-base font-semibold text-ink">页面出错了</p>
            <p className="mt-1 text-sm text-muted">
              渲染组件时发生异常，请刷新页面重试。
            </p>
          </div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex min-h-10 items-center gap-2 rounded-2xl bg-brandSolid px-4 text-sm font-medium text-onBrand shadow-card transition hover:brightness-105 active:scale-95"
          >
            <RotateCw size={15} />
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
