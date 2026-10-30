import { BarChart2, Keyboard, LogOut, Moon, Newspaper, Radar, Settings2, Sparkles, Sun } from 'lucide-react'
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
  onOpenHelp?: () => void
  onLogout: () => void
  theme: Theme
  onToggleTheme: () => void
}

function ActionButton({
  icon: Icon,
  label,
  danger = false,
  onClick,
}: {
  icon: LucideIcon
  label: string
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`
        flex h-10 w-10 items-center justify-center rounded-lg text-text-muted
        transition-colors duration-150 hover:bg-bg-hover touch:h-11 touch:w-11
        ${danger ? 'hover:text-accent-red' : 'hover:text-text-primary'}
      `}
    >
      <Icon className="h-[18px] w-[18px]" />
    </button>
  )
}

async function logout(onLogout: () => void) {
  await fetch('/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
  onLogout()
}

function BrandMark({ size = 'md' }: { size?: 'sm' | 'md' }) {
  return (
    <div
      className={`
        flex flex-shrink-0 items-center justify-center rounded-lg bg-accent-blue text-on-accent
        ${size === 'sm' ? 'h-8 w-8' : 'h-9 w-9'}
      `}
      title="MakhalReader"
    >
      <Radar className="h-[18px] w-[18px]" strokeWidth={2.25} />
    </div>
  )
}

/** Vertical rail (iPad and desktop): main views with labels, app-level actions below. */
export function NavRail({ view, onViewChange, onOpenFeedManager, onOpenHelp, onLogout, theme, onToggleTheme }: NavProps) {
  return (
    <nav
      aria-label="Navigation principale"
      className="flex h-full w-16 flex-shrink-0 flex-col items-center border-r border-border-subtle bg-bg-surface pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3"
    >
      <div className="mb-5">
        <BrandMark />
      </div>

      <div className="flex w-full flex-col items-center gap-1 px-1.5">
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
                group flex w-full flex-col items-center gap-1 rounded-lg py-2 text-[10px] font-medium
                transition-colors duration-150
                ${active ? 'text-accent-blue' : 'text-text-muted hover:text-text-primary'}
              `}
            >
              <span
                className={`
                  flex h-8 w-11 items-center justify-center rounded-full transition-colors duration-150
                  ${active ? 'bg-accent-blue/14' : 'group-hover:bg-bg-hover'}
                `}
              >
                <Icon className="h-[18px] w-[18px]" />
              </span>
              {v.label}
            </button>
          )
        })}
      </div>

      <div className="mt-auto flex flex-col items-center gap-1">
        <ActionButton icon={Settings2} label="Gérer les sources" onClick={onOpenFeedManager} />
        <ActionButton
          icon={theme === 'light' ? Moon : Sun}
          label={theme === 'light' ? 'Passer en mode sombre' : 'Passer en mode clair'}
          onClick={onToggleTheme}
        />
        {onOpenHelp && <ActionButton icon={Keyboard} label="Raccourcis clavier  ?" onClick={onOpenHelp} />}
        <ActionButton icon={LogOut} label="Se déconnecter" danger onClick={() => logout(onLogout)} />
      </div>
    </nav>
  )
}

/** Phone header: brand + app-level actions. */
export function MobileHeader({
  onOpenFeedManager,
  onLogout,
  theme,
  onToggleTheme,
}: Omit<NavProps, 'view' | 'onViewChange'>) {
  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-border-subtle bg-bg-surface px-3">
      <div className="flex min-w-0 items-center gap-2.5">
        <BrandMark size="sm" />
        <h1 className="truncate text-[15px] font-semibold text-text-primary">MakhalReader</h1>
      </div>
      <div className="flex items-center gap-0.5">
        <ActionButton icon={Settings2} label="Gérer les sources" onClick={onOpenFeedManager} />
        <ActionButton
          icon={theme === 'light' ? Moon : Sun}
          label={theme === 'light' ? 'Passer en mode sombre' : 'Passer en mode clair'}
          onClick={onToggleTheme}
        />
        <ActionButton icon={LogOut} label="Se déconnecter" danger onClick={() => logout(onLogout)} />
      </div>
    </header>
  )
}

/** Phone tab bar: the three main views, clear of the home indicator. */
export function MobileNavBar({ view, onViewChange }: Pick<NavProps, 'view' | 'onViewChange'>) {
  return (
    <nav
      aria-label="Navigation principale"
      className="flex flex-shrink-0 border-t border-border-subtle bg-bg-surface pb-[env(safe-area-inset-bottom)]"
    >
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
              flex flex-1 flex-col items-center gap-0.5 pb-1.5 pt-2 text-[11px] font-medium
              transition-colors duration-150
              ${active ? 'text-accent-blue' : 'text-text-muted'}
            `}
          >
            <span
              className={`flex h-7 w-12 items-center justify-center rounded-full transition-colors ${active ? 'bg-accent-blue/14' : ''}`}
            >
              <Icon className="h-5 w-5" />
            </span>
            <span>{v.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
