import { Search, PanelLeftClose, PanelLeftOpen } from 'lucide-react'

interface TopbarProps {
  breadcrumb: string
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onSearch?: (q: string) => void
}

export function Topbar({ breadcrumb, sidebarOpen, onToggleSidebar }: TopbarProps) {
  return (
    <div className="h-[48px] min-h-[48px] border-b border-border-subtle flex items-center px-5 gap-3 bg-bg-base">
      <button 
        onClick={onToggleSidebar}
        className="text-text-muted hover:text-text-primary transition-colors flex-shrink-0"
        title={sidebarOpen ? "Hide sidebar [" : "Show sidebar ["}
      >
        {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
      </button>

      <div className="flex items-center gap-1.5 text-[13px] text-text-muted">
        <span>Baṣīra</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
        <b className="text-text-primary font-medium">{breadcrumb}</b>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        <div className="flex items-center gap-1.5 bg-bg-surface border border-border-default rounded-md px-3 py-1.5 text-[13px] text-text-muted max-w-[250px] cursor-text">
          <Search size={13} />
          <span>Rechercher…</span>
        </div>
      </div>
    </div>
  )
}
