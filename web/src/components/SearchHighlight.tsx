import {Fragment} from 'react'
import {splitSearchHighlights, type SearchHighlightMode} from '../lib/searchHighlight'

export function SearchHighlight({
  text,
  query,
  mode = 'literal',
}: {
  text: string
  query: string
  mode?: SearchHighlightMode
}) {
  const parts = splitSearchHighlights(text, query, mode)

  return (
    <>
      {parts.map((part, index) => (
        <Fragment key={`${part.highlighted ? 'h' : 't'}-${index}`}>
          {part.highlighted ? (
            <mark className="rounded-sm bg-warning/30 px-0.5 text-inherit">
              {part.text}
            </mark>
          ) : (
            part.text
          )}
        </Fragment>
      ))}
    </>
  )
}
