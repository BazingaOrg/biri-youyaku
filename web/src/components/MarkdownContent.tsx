import ReactMarkdown from 'react-markdown'

export function MarkdownContent({markdown}: {markdown: string}) {
  return <ReactMarkdown>{markdown}</ReactMarkdown>
}
