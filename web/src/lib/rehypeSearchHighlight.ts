import type {Element, Root, RootContent} from 'hast'
import {splitSearchHighlights} from './searchHighlight'

export function rehypeSearchHighlight({query}: {query: string}) {
  return (tree: Root) => {
    if (!query.trim()) return
    const visit = (parent: Root | Element) => {
      parent.children = parent.children.flatMap((node): RootContent[] => {
        if (node.type === 'element') {
          if (!['mark', 'script', 'style'].includes(node.tagName)) visit(node)
          return [node]
        }
        if (node.type !== 'text') return [node]
        return splitSearchHighlights(node.value, query, 'fts').map((part): RootContent =>
          part.highlighted
            ? {
                type: 'element',
                tagName: 'mark',
                properties: {className: ['search-highlight'], 'data-find-hit': ''},
                children: [{type: 'text', value: part.text}],
              }
            : {type: 'text', value: part.text},
        )
      }) as typeof parent.children
    }
    visit(tree)
  }
}
