import {lazy, Suspense} from 'react'
import {PROSE} from '../lib/prose'

const MarkdownContent = lazy(() =>
  import('./MarkdownContent').then((module) => ({default: module.MarkdownContent})),
)

export function LazyMarkdown({markdown}: {markdown: string}) {
  return (
    <div className={PROSE}>
      <Suspense fallback={<p className="whitespace-pre-wrap">{markdown}</p>}>
        <MarkdownContent markdown={markdown} />
      </Suspense>
    </div>
  )
}
