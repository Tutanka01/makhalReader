import { ArrowLeft, CalendarDays, RefreshCw, Sparkles } from 'lucide-react'

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
    <div className="flex flex-shrink-0 items-center justify-between border-b border-border-subtle bg-bg-surface px-3 py-2">
      <div className="flex items-center gap-1">
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="hidden p-1.5 rounded-lg text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary lg:flex"
            title={sidebarOpen ? 'Hide sidebar  [' : 'Show sidebar  ['}
          >
            {sidebarOpen ? <PanelLeftCloseIcon /> : <PanelLeftOpenIcon />}
          </button>
        )}
        {onBack && (
          <button
            onClick={onBack}
            className="p-1.5 rounded-lg text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
            aria-label="Retour aux articles"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
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

// Mirrors the inline panel icons used by ReaderView's toolbar for visual consistency.
function PanelLeftCloseIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2"/>
      <path d="M9 3v18"/>
      <path d="m16 15-3-3 3-3"/>
    </svg>
  )
}

function PanelLeftOpenIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2"/>
      <path d="M9 3v18"/>
      <path d="m14 9 3 3-3 3"/>
    </svg>
  )
}
