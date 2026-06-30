import { ArrowLeft } from 'lucide-react'
import type { Briefing } from '../../types'
import { BriefingHero } from './BriefingHero'
import { TopPicks } from './TopPicks'
import { BriefingSection } from './BriefingSection'

interface Props {
  briefing: Briefing
  onOpen: (id: number) => void
  /** Mobile-only "back to list" affordance, rendered above the hero when present. */
  onBackToList?: () => void
}

export function BriefingContentPane({ briefing, onOpen, onBackToList }: Props) {
  return (
    <div className="space-y-7">
      {onBackToList && (
        <button
          onClick={onBackToList}
          className="briefing-rise flex items-center gap-1.5 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Retour à l'historique
        </button>
      )}
      <BriefingHero
        content={briefing.content}
        generatedAt={briefing.generated_at}
        articleCount={briefing.article_count}
      />
      <TopPicks ids={briefing.content.top_picks} articles={briefing.content.articles} onOpen={onOpen} />
      <div className="space-y-6">
        {briefing.content.sections.map((section, i) => (
          <BriefingSection
            key={i}
            section={section}
            articles={briefing.content.articles}
            index={i}
            onOpen={onOpen}
          />
        ))}
      </div>
    </div>
  )
}
