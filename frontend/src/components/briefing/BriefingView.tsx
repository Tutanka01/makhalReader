import { Newspaper, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import { useBriefing } from '../../hooks/useBriefing'
import { BriefingHero } from './BriefingHero'
import { TopPicks } from './TopPicks'
import { BriefingSection } from './BriefingSection'
import { BriefingSkeleton } from './BriefingSkeleton'

export function BriefingView({
  onOpen,
  onBackToFeed,
}: {
  onOpen: (id: number) => void
  onBackToFeed?: () => void
}) {
  const { briefing, status, generate } = useBriefing()

  const Shell = ({ children }: { children: ReactNode }) => (
    <div className="h-full overflow-y-auto bg-bg-base">
      <div className="mx-auto w-full max-w-[980px] px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
        {onBackToFeed && (
          <div className="mb-4 lg:hidden">
            <button
              onClick={onBackToFeed}
              className="inline-flex items-center gap-2 rounded-md border border-border-default px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
            >
              <Newspaper className="h-4 w-4" />
              Articles
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  )

  if (status === 'loading') return <Shell><BriefingSkeleton /></Shell>

  if (status === 'empty' || status === 'error' || !briefing) {
    return (
      <Shell>
        <div className="mx-auto flex max-w-sm flex-col items-center justify-center py-24 text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-md border border-border-default bg-bg-surface text-accent-blue">
            <Sparkles className="h-5 w-5" />
          </div>
          <h2 className="text-base font-semibold text-text-primary">
            {status === 'error' ? 'Briefing indisponible' : 'Pas encore de briefing'}
          </h2>
          <p className="mb-6 mt-1 max-w-xs text-xs leading-relaxed text-text-muted">
            Synthétise les meilleurs articles des dernières 24h en une lecture de 5 minutes.
          </p>
          <button
            onClick={generate}
            disabled={status === 'generating'}
            className="flex items-center gap-2 rounded-md bg-accent-blue px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            Générer le briefing
          </button>
        </div>
      </Shell>
    )
  }

  if (status === 'generating') return <Shell><BriefingSkeleton /></Shell>

  const { content } = briefing
  return (
    <Shell>
      <div className="space-y-7">
        <BriefingHero
          content={content}
          generatedAt={briefing.generated_at}
          articleCount={briefing.article_count}
          generating={false}
          onRegenerate={generate}
        />
        <TopPicks ids={content.top_picks} articles={content.articles} onOpen={onOpen} />
        <div className="space-y-6">
          {content.sections.map((section, i) => (
            <BriefingSection key={i} section={section} articles={content.articles} index={i} onOpen={onOpen} />
          ))}
        </div>
      </div>
    </Shell>
  )
}
