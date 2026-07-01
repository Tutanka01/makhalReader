import { ArrowLeft, CalendarDays, PanelLeftClose, PanelLeftOpen, RefreshCw, Sparkles } from 'lucide-react'
import { IconButton } from '../ui'

type Mode = 'live' | 'history'

interface Props {
  sidebarOpen?: boolean
  onToggleSidebar?: () => void
  onBack?: () => void
  onRegenerate: () => void
  regenerating: boolean
  /** Only a briefing that exists (or is being generated) can be regenerated. */
  showRegenerate: boolean
  mode: Mode
  onToggleMode: () => void
}

export function BriefingToolbar({
  sidebarOpen,
  onToggleSidebar,
  onBack,
  onRegenerate,
  regenerating,
  showRegenerate,
  mode,
  onToggleMode,
}: Props) {
  return (
    <div className="flex flex-shrink-0 items-center justify-between border-b border-border-subtle bg-bg-surface/95 px-3 py-2">
      <div className="flex items-center gap-1">
        {onToggleSidebar && (
          <IconButton
            onClick={onToggleSidebar}
            icon={sidebarOpen ? PanelLeftClose : PanelLeftOpen}
            label={sidebarOpen ? 'Masquer la sidebar  [' : 'Afficher la sidebar  ['}
            className="hidden lg:inline-flex"
          />
        )}
        {onBack && (
          <IconButton
            onClick={onBack}
            icon={ArrowLeft}
            label="Retour aux articles"
          />
        )}
        <span className="ml-1 flex items-center gap-1.5 text-sm font-semibold text-text-primary">
          <Sparkles className="h-3.5 w-3.5 text-accent-blue" />
          {mode === 'history' ? 'Archive' : 'Briefing'}
        </span>
      </div>

      <div className="flex items-center gap-1">
        <button
          onClick={onToggleMode}
          className={`flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors hover:bg-bg-hover hover:text-text-primary ${
            mode === 'history' ? 'bg-accent-blue/10 text-accent-blue' : 'text-text-secondary'
          }`}
          title={mode === 'history' ? "Revenir au briefing du jour" : "Voir l'historique des briefings"}
        >
          <CalendarDays className="h-4 w-4" />
          <span className="hidden sm:inline">Archive</span>
        </button>

        {showRegenerate && (
          <button
            onClick={onRegenerate}
            disabled={regenerating}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
            title="Régénérer le briefing"
          >
            <RefreshCw className={`h-4 w-4 ${regenerating ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{regenerating ? 'Synthèse…' : 'Régénérer'}</span>
          </button>
        )}
      </div>
    </div>
  )
}
