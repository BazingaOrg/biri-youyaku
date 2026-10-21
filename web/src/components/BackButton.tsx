import {ArrowLeft} from 'lucide-react'
import {Link} from 'wouter'

export function BackButton({href = '/', label = '返回'}: {href?: string; label?: string}) {
  return (
    <Link
      href={href}
      className="inline-flex min-h-10 w-fit max-w-full items-center gap-2 rounded-2xl px-1 text-sm text-muted transition-colors hover:text-brand"
    >
      <ArrowLeft size={16} className="shrink-0" />
      <span className="min-w-0 truncate">{label}</span>
    </Link>
  )
}
