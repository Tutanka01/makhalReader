import { Rss, Sparkles, BarChart2, Network, BookOpen, LogOut, Bookmark, AlertTriangle, Users, FileText, Calendar, Layers, BookMarked, RadioTower, Settings, Shield } from 'lucide-react'
import { useCallback, useState } from 'react'
import type { NotificationCounts } from '../types'
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'
import { usePolling } from '../hooks/usePolling'
import { useCurrentUser } from '../context/UserContext'

export type AppView = 'feed' | 'digest' | 'stats' | 'research' | 'litreview' | 'threats' | 'authors' | 'write' | 'conferences' | 'highlights' | 'bibliography' | 'feed-manager' | 'admin'

interface SidebarProps {
  currentView: AppView
  onViewChange: (v: AppView) => void
  feeds: Feed[]
  onOpenProfile: () => void
  onOpenSettings: () => void
  onLogout: () => void
}

const NO_NOTIFICATIONS: NotificationCounts = { new_threats: 0, urgent_deadlines: 0, new_author_papers: 0 }

function dismissNotification(type: 'threats' | 'conferences' | 'authors') {
  fetch('/api/research/notifications/dismiss', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type }),
  }).catch(() => {})
}

export function Sidebar({
  currentView,
  onViewChange,
  feeds,
  onOpenProfile,
  onOpenSettings,
  onLogout
}: SidebarProps) {
  const { filter, setFilter, articles } = useArticlesStore()
  const { user } = useCurrentUser()
  const initials = user?.display_name
    ? user.display_name.split(' ').map(s => s[0]).join('').toUpperCase().slice(0, 2)
    : '?'
  const [notifications, setNotifications] = useState<NotificationCounts>(NO_NOTIFICATIONS)

  const fetchNotifications = useCallback(() => {
    if (currentView === 'conferences' || currentView === 'threats' || currentView === 'authors') return
    fetch('/api/research/notifications', { credentials: 'include' })
      .then(r => r.ok ? r.json() : NO_NOTIFICATIONS)
      .then(data => setNotifications(data))
      .catch(() => {})
  }, [currentView])

  usePolling(fetchNotifications, 60_000)

  const handleNavClick = useCallback((view: AppView, dismissType?: 'threats' | 'conferences' | 'authors') => {
    if (dismissType) {
      const next = { ...notifications }
      if (dismissType === 'threats') next.new_threats = 0
      else if (dismissType === 'conferences') next.urgent_deadlines = 0
      else if (dismissType === 'authors') next.new_author_papers = 0
      setNotifications(next)
      dismissNotification(dismissType)
    }
    onViewChange(view)
  }, [notifications, onViewChange])

  const categories = ['All', ...Array.from(new Set(feeds.map(f => f.category))).sort()]
  const activeCategory = filter.bookmarked ? 'Bookmarks' : (filter.category ?? 'All')

  const feedNameToCategory = new Map(feeds.map(f => [f.name, f.category]))
  const categoryCounts = new Map<string, number>()
  let bookmarkCount = 0
  for (const a of articles) {
    if (filter.status === 'read') continue
    if (a.bookmarked) bookmarkCount++
    const cat = feedNameToCategory.get(a.feed_name)
    if (cat) categoryCounts.set(cat, (categoryCounts.get(cat) ?? 0) + 1)
  }
  const totalCount = [...categoryCounts.values()].reduce((s, n) => s + n, 0)

  const handleCategoryClick = (cat: string) => {
    onViewChange('feed')
    if (cat === 'Bookmarks') {
      setFilter({ bookmarked: true, category: null })
    } else if (cat === 'All') {
      setFilter({ bookmarked: false, category: null })
    } else {
      setFilter({ bookmarked: false, category: cat })
    }
  }

  const NavItem = ({ icon: Icon, label, active, count, dot, onClick }: any) => (
    <div
      onClick={onClick}
      className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors text-[13.5px] select-none mb-[1px]
        ${active ? 'bg-bg-elevated text-text-primary font-medium' : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'}`}
    >
      <div className={`flex items-center justify-center flex-shrink-0 w-[18px] h-[18px] ${active ? 'opacity-90' : 'opacity-55'}`}>
        <Icon size={15} strokeWidth={2} />
      </div>
      <span className="flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{label}</span>
      {dot && (
        <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
      )}
      {count !== undefined && count > 0 && (
        <span className="text-[11px] text-text-muted bg-bg-elevated rounded-full px-2 py-[1px] font-medium font-mono">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </div>
  )

  const CatItem = ({ colorClass, label, active, count, onClick }: any) => (
    <div
      onClick={onClick}
      className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors text-[13.5px] select-none mb-[1px]
        ${active ? 'bg-bg-elevated text-text-primary font-medium' : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'}`}
    >
      <div className={`w-[7px] h-[7px] rounded-full flex-shrink-0 ml-[2px] ${colorClass}`} />
      <span className="flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{label}</span>
      {count !== undefined && count > 0 && (
        <span className="text-[11px] text-text-muted bg-bg-elevated rounded-full px-2 py-[1px] font-medium font-mono">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </div>
  )

  const colors = ['bg-[#2F6FED]', 'bg-[#0F7B6C]', 'bg-[#B45309]', 'bg-[#6B4FBB]', 'bg-[#9B9B9B]']

  return (
    <aside style={{ backgroundColor: 'var(--sidebar-bg)' }} className="w-[240px] min-w-[240px] border-r border-border-subtle flex flex-col h-screen overflow-y-auto overflow-x-hidden z-10">
      <div className="h-[52px] px-3 flex items-center gap-2 border-b border-border-subtle flex-shrink-0">
        <img src="/logo.png" alt="Logo" className="w-6 h-6 rounded object-cover flex-shrink-0" />
        <span className="text-sm font-semibold tracking-tight text-text-primary">Baṣīra</span>
      </div>

      <div className="px-2 pt-4 pb-1.5">
        <div className="text-[11px] font-medium text-text-muted tracking-wider uppercase px-2 pb-1.5">Principal</div>
        <NavItem icon={Rss} label="Feed" active={currentView === 'feed' && activeCategory === 'All'} count={totalCount} onClick={() => handleCategoryClick('All')} />
        <NavItem icon={Bookmark} label="Bookmarks" active={currentView === 'feed' && activeCategory === 'Bookmarks'} count={bookmarkCount} onClick={() => handleCategoryClick('Bookmarks')} />
        <NavItem icon={Sparkles} label="Digest" active={currentView === 'digest'} onClick={() => onViewChange('digest')} />
        <NavItem icon={BookOpen} label="Lit Review" active={currentView === 'litreview'} onClick={() => onViewChange('litreview')} />
        <NavItem icon={Network} label="Clusters" active={currentView === 'research'} onClick={() => onViewChange('research')} />
        <NavItem icon={Layers} label="Highlights" active={currentView === 'highlights'} onClick={() => onViewChange('highlights')} />
        <NavItem icon={Users} label="Authors" active={currentView === 'authors'} count={notifications.new_author_papers} onClick={() => handleNavClick('authors', 'authors')} />
        <NavItem icon={AlertTriangle} label="Threats" active={currentView === 'threats'} count={notifications.new_threats} onClick={() => handleNavClick('threats', 'threats')} />
        <NavItem icon={FileText} label="Writing" active={currentView === 'write'} onClick={() => onViewChange('write')} />
        <NavItem icon={Calendar} label="Conferences" active={currentView === 'conferences'} count={notifications.urgent_deadlines} onClick={() => handleNavClick('conferences', 'conferences')} />
        <NavItem icon={BookMarked} label="Bibliography" active={currentView === 'bibliography'} onClick={() => onViewChange('bibliography')} />
        <NavItem icon={RadioTower} label="Feed Manager" active={currentView === 'feed-manager'} onClick={() => onViewChange('feed-manager')} />
        <NavItem icon={BarChart2} label="Stats" active={currentView === 'stats'} onClick={() => onViewChange('stats')} />
        {user?.role === 'admin' && (
          <NavItem icon={Shield} label="Lab Admin" active={currentView === 'admin'} onClick={() => onViewChange('admin')} />
        )}
      </div>

      <div className="h-[1px] bg-border-subtle mx-4 my-2" />

      <div className="px-2 pt-2 pb-1.5">
        <div className="text-[11px] font-medium text-text-muted tracking-wider uppercase px-2 pb-1.5">Feeds</div>
        {categories.filter(c => c !== 'All').map((cat, i) => {
          const count = categoryCounts.get(cat) ?? 0
          return (
            <CatItem
              key={cat}
              colorClass={colors[i % colors.length]}
              label={cat}
              active={currentView === 'feed' && activeCategory === cat}
              count={count}
              onClick={() => handleCategoryClick(cat)}
            />
          )
        })}
      </div>

      <div className="mt-auto p-2 border-t border-border-subtle">
        <div onClick={onOpenProfile} className="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors hover:bg-bg-hover">
          <div className="w-7 h-7 rounded-full bg-text-primary text-white flex items-center justify-center text-[10px] font-semibold flex-shrink-0 tracking-wide">
            {initials}
          </div>
          <div className="flex-1">
            <div className="text-[12.5px] font-medium text-text-primary leading-tight">{user?.display_name ?? 'User'}</div>
            <div className="text-[11px] text-text-muted leading-tight">{user?.role ?? 'User'}</div>
          </div>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onOpenSettings() }}
            className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-text-primary transition-colors"
            title="Settings"
          >
            <Settings size={14} />
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onLogout() }}
            className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-danger transition-colors"
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>

      </div>
    </aside>
  )
}
