import ReactMarkdown from 'react-markdown'
import {rehypeSearchHighlight} from '../lib/rehypeSearchHighlight'

export function MarkdownContent({markdown, query = ''}: {markdown: string; query?: string}) {
  return <ReactMarkdown rehypePlugins={query ? [[rehypeSearchHighlight, {query}]] : []}>{markdown}</ReactMarkdown>
}
