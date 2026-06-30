import { Sparkles } from 'lucide-react'
import { useBriefing } from '../../hooks/useBriefing'
import { BriefingHero } from './BriefingHero'
import { TopPicks } from './TopPicks'
import { BriefingSection } from './BriefingSection'
import { BriefingSkeleton } from './BriefingSkeleton'
import { BriefingToolbar } from './BriefingToolbar'

interface Props {
  onOpen: (id: number) => void
  /** Desktop sidebar control — omitted on mobile, where there's no persistent sidebar. */
  sidebarOpen?: boolean
  onToggleSidebar?: () => void
  /** Mobile back-to-feed control — omitted on desktop, where the sidebar stays visible. */
  onBack?: () => void
}

export function BriefingView({ onOpen, sidebarOpen, onToggleSidebar, onBack }: Props) {
  const { briefing, status, generate } = useBriefing()

  const isFirstGenerate = status === 'generating' && !briefing
  const isRegenerating = status === 'generating' && !!briefing

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg-base">
      <BriefingToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={onToggleSidebar}
        onBack={onBack}
        onRegenerate={generate}
        regenerating={status === 'generating'}
        showRegenerate={status === 'ready' || status === 'generating'}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[980px] px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
          {(status === 'loading' || isFirstGenerate) && <BriefingSkeleton />}

          {(status === 'empty' || status === 'error') && (
            <EmptyState status={status} onGenerate={generate} />
          )}

          {briefing && status !== 'loading' && (
            <div className="space-y-7">
              {isRegenerating && (
                <div className="briefing-rise flex items-center gap-2 rounded-md border border-accent-blue/30 bg-accent-blue/10 px-3 py-2 text-xs text-accent-blue">
                  <Sparkles className="h-3.5 w-3.5 animate-pulse" />
                  Régénération en cours — le briefing ci-dessous est encore le précédent.
                </div>
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
          )}
        </div>
      </div>
    </div>
  )
}

function EmptyState({ status, onGenerate }: { status: 'empty' | 'error'; onGenerate: () => void }) {
  return (
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
        onClick={onGenerate}
        className="flex items-center gap-2 rounded-md bg-accent-blue px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
      >
        <Sparkles className="h-4 w-4" />
        Générer le briefing
      </button>
    </div>
  )
}
