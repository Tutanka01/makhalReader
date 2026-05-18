import { Rss, Sparkles, BarChart2, Network, BookOpen, Settings, LogOut, Bookmark } from 'lucide-react'
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'

export type AppView = 'feed' | 'digest' | 'stats' | 'research' | 'litreview'

interface SidebarProps {
  currentView: AppView
  onViewChange: (v: AppView) => void
  feeds: Feed[]
  onOpenFeedManager: () => void
  onOpenProfile: () => void
  onLogout: () => void
}

export function Sidebar({
  currentView,
  onViewChange,
  feeds,
  onOpenFeedManager,
  onOpenProfile,
  onLogout
}: SidebarProps) {
  const { filter, setFilter, articles } = useArticlesStore()

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

  const NavItem = ({ icon: Icon, label, active, count, onClick }: any) => (
    <div
      onClick={onClick}
      className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors text-[13.5px] select-none mb-[1px]
        ${active ? 'bg-bg-elevated text-text-primary font-medium' : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'}`}
    >
      <div className={`flex items-center justify-center flex-shrink-0 w-[18px] h-[18px] ${active ? 'opacity-90' : 'opacity-55'}`}>
        <Icon size={15} strokeWidth={2} />
      </div>
      <span className="flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{label}</span>
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
        <NavItem icon={BarChart2} label="Stats" active={currentView === 'stats'} onClick={() => onViewChange('stats')} />
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
            AF
          </div>
          <div className="flex-1">
            <div className="text-[12.5px] font-medium text-text-primary leading-tight">Arona</div>
            <div className="text-[11px] text-text-muted leading-tight">Admin</div>
          </div>
          <div onClick={(e) => { e.stopPropagation(); onLogout() }} className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-danger transition-colors" title="Logout">
            <LogOut size={14} />
          </div>
        </div>
        <div onClick={onOpenFeedManager} className="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors hover:bg-bg-hover mt-0.5">
          <div className="w-7 h-7 rounded-full bg-[#6B4FBB] text-white flex items-center justify-center text-[10px] font-semibold flex-shrink-0 tracking-wide">
            <Settings size={14} />
          </div>
          <div>
            <div className="text-[12.5px] font-medium text-text-primary leading-tight">Feed Manager</div>
            <div className="text-[11px] text-text-muted leading-tight">Manage sources</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
