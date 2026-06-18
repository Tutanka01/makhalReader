import { RefreshCw } from 'lucide-react'
import { format, formatDistanceToNow } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { BriefingContent } from '../../types'

interface Props {
  content: BriefingContent
  generatedAt: string
  articleCount: number
  generating: boolean
  onRegenerate: () => void
}

export function BriefingHero({ content, generatedAt, articleCount, generating, onRegenerate }: Props) {
  const today = format(new Date(generatedAt), 'EEEE d MMMM', { locale: fr })
  const ago = formatDistanceToNow(new Date(generatedAt), { addSuffix: true, locale: fr })

  return (
    <header className="briefing-rise" style={{ animationDelay: '0ms' }}>
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-text-muted">Briefing</p>
      <h1 className="mt-1 text-2xl font-bold capitalize tracking-tight text-text-primary">{today}</h1>
      {content.intro && (
        <p className="reader-content mt-4 text-[17px] leading-relaxed text-text-secondary">{content.intro}</p>
      )}
      <div className="mt-4 flex items-center gap-3 text-xs text-text-muted">
        <span className="tabular-nums">{articleCount} articles · {content.sections.length} thèmes</span>
        <span aria-hidden>·</span>
        <span>généré {ago}</span>
        <button
          onClick={onRegenerate}
          disabled={generating}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-border-default px-2.5 py-1 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${generating ? 'animate-spin' : ''}`} />
          {generating ? 'Génération…' : 'Régénérer'}
        </button>
      </div>
      <div className="mt-6 h-px w-full bg-border-subtle" />
    </header>
  )
}
