import { CalendarDays, FileText, Layers3, Star } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { BriefingContent } from '../../types'
import { totalMinutes } from './format'

interface Props {
  content: BriefingContent
  generatedAt: string
  articleCount: number
}

function Metric({
  icon: Icon,
  value,
  label,
  accent,
}: {
  icon: LucideIcon
  value: number | string
  label: string
  accent?: boolean
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md border border-border-subtle bg-bg-surface px-3 py-2">
      <Icon className={`h-4 w-4 flex-shrink-0 ${accent ? 'text-accent-blue' : 'text-text-muted'}`} />
      <span className="min-w-0">
        <span className={`block text-sm font-semibold tabular-nums ${accent ? 'text-accent-blue' : 'text-text-primary'}`}>
          {value}
        </span>
        <span className="block truncate text-[11px] text-text-muted">{label}</span>
      </span>
    </div>
  )
}

export function BriefingHero({ content, generatedAt, articleCount }: Props) {
  const date = new Date(generatedAt)
  const dateline = format(date, 'EEEE d MMMM yyyy', { locale: fr })
  const stamp = format(date, 'HH:mm', { locale: fr })

  const picks = content.top_picks
    .map((id) => content.articles[String(id)])
    .filter(Boolean)
  const minutes = totalMinutes(picks)

  return (
    <header className="briefing-rise">
      <div className="border-b border-border-subtle pb-5">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-text-muted">
          <span className="inline-flex items-center gap-1.5 capitalize">
            <CalendarDays className="h-3.5 w-3.5" />
            {dateline}
          </span>
          <span className="text-border-default">·</span>
          <span>généré à {stamp}</span>
        </div>
        <h1 className="text-3xl font-semibold leading-tight text-text-primary sm:text-4xl">
          Le Briefing
        </h1>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        {content.intro && (
          <p className="reader-content text-[18px] leading-relaxed text-text-secondary sm:text-[19px]">
            {content.intro}
          </p>
        )}

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-2">
          <Metric icon={FileText} value={articleCount} label="articles retenus" />
          <Metric icon={Layers3} value={content.sections.length} label="thèmes" />
          <Metric icon={Star} value={content.top_picks.length} label="priorités" accent />
          <Metric icon={CalendarDays} value={minutes ? `${minutes} min` : 'n/a'} label="lecture estimée" />
        </div>
      </div>
    </header>
  )
}
