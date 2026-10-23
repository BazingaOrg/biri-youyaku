import {Fragment} from 'react'
import {splitSearchHighlights, type SearchHighlightMode} from '../lib/searchHighlight'

export function SearchHighlight({
  text,
  query,
  mode = 'literal',
  navigable = false,
}: {
  text: string
  query: string
  mode?: SearchHighlightMode
  navigable?: boolean
}) {
  const parts = splitSearchHighlights(text, query, mode)

  return (
    <>
      {parts.map((part, index) => (
        <Fragment key={`${part.highlighted ? 'h' : 't'}-${index}`}>
          {part.highlighted ? (
            <mark className="search-highlight" data-find-hit={navigable ? '' : undefined}>
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
