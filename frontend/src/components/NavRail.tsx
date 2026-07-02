import { BarChart2, LogOut, Moon, Newspaper, Radar, Settings2, Sparkles, Sun } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Theme } from '../theme'

export type AppView = 'briefing' | 'feed' | 'stats'

const VIEWS: Array<{ value: AppView; label: string; icon: LucideIcon }> = [
  { value: 'briefing', label: 'Briefing', icon: Sparkles },
  { value: 'feed', label: 'Articles', icon: Newspaper },
  { value: 'stats', label: 'Stats', icon: BarChart2 },
]

interface NavProps {
  view: AppView
  onViewChange: (v: AppView) => void
  onOpenFeedManager: () => void
  onLogout: () => void
  theme: Theme
  onToggleTheme: () => void
}

function RailButton({
  icon: Icon,
  label,
  active = false,
  danger = false,
  onClick,
}: {
  icon: LucideIcon
  label: string
  active?: boolean
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      className={`
        relative flex h-10 w-10 items-center justify-center rounded-lg
        transition-colors duration-150
        ${active
          ? 'bg-accent-blue/12 text-accent-blue'
          : `text-text-muted hover:bg-bg-hover ${danger ? 'hover:text-accent-red' : 'hover:text-text-primary'}`
        }
      `}
    >
      <Icon className="h-[18px] w-[18px]" />
      {active && (
        <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-accent-blue" />
      )}
    </button>
  )
}

async function logout(onLogout: () => void) {
  await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
  onLogout()
}

/** Desktop-only vertical rail: global navigation + app-level actions. */
export function NavRail({ view, onViewChange, onOpenFeedManager, onLogout, theme, onToggleTheme }: NavProps) {
  return (
    <nav className="flex h-full w-14 flex-shrink-0 flex-col items-center border-r border-border-subtle bg-bg-surface py-3">
      <div
        className="mb-5 flex h-9 w-9 items-center justify-center rounded-lg border border-accent-blue/20 bg-accent-blue/12 text-accent-blue"
        title="MakhalReader — Cockpit de veille personnelle"
      >
        <Radar className="h-4 w-4" />
      </div>

      <div className="flex flex-col items-center gap-1">
        {VIEWS.map(v => (
          <RailButton
            key={v.value}
            icon={v.icon}
            label={v.label}
            active={view === v.value}
            onClick={() => onViewChange(v.value)}
          />
        ))}
      </div>

      <div className="mt-auto flex flex-col items-center gap-1">
        <RailButton icon={Settings2} label="Gérer les feeds" onClick={onOpenFeedManager} />
        <RailButton
          icon={theme === 'light' ? Moon : Sun}
          label={theme === 'light' ? 'Passer en mode sombre' : 'Passer en mode clair'}
          onClick={onToggleTheme}
        />
        <RailButton icon={LogOut} label="Se déconnecter" danger onClick={() => logout(onLogout)} />
      </div>
    </nav>
  )
}

/** Mobile-only compact header: brand + app-level actions. */
export function MobileHeader({
  onOpenFeedManager,
  onLogout,
  theme,
  onToggleTheme,
}: Omit<NavProps, 'view' | 'onViewChange'>) {
  return (
    <header className="flex flex-shrink-0 items-center justify-between border-b border-border-subtle bg-bg-surface px-3 py-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent-blue/20 bg-accent-blue/12 text-accent-blue">
          <Radar className="h-4 w-4" />
        </div>
        <h1 className="truncate text-sm font-semibold text-text-primary">MakhalReader</h1>
      </div>
      <div className="flex items-center gap-0.5">
        <RailButton icon={Settings2} label="Gérer les feeds" onClick={onOpenFeedManager} />
        <RailButton
          icon={theme === 'light' ? Moon : Sun}
          label={theme === 'light' ? 'Passer en mode sombre' : 'Passer en mode clair'}
          onClick={onToggleTheme}
        />
        <RailButton icon={LogOut} label="Se déconnecter" danger onClick={() => logout(onLogout)} />
      </div>
    </header>
  )
}

/** Mobile-only bottom tab bar: the three main views. */
export function MobileNavBar({ view, onViewChange }: Pick<NavProps, 'view' | 'onViewChange'>) {
  return (
    <nav className="flex flex-shrink-0 border-t border-border-subtle bg-bg-surface pb-[env(safe-area-inset-bottom)]">
      {VIEWS.map(v => {
        const Icon = v.icon
        const active = view === v.value
        return (
          <button
            key={v.value}
            type="button"
            onClick={() => onViewChange(v.value)}
            aria-current={active ? 'page' : undefined}
            className={`
              flex flex-1 flex-col items-center gap-1 py-2 text-[10px] font-medium
              transition-colors duration-150
              ${active ? 'text-accent-blue' : 'text-text-muted hover:text-text-primary'}
            `}
          >
            <Icon className="h-5 w-5" />
            <span>{v.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
