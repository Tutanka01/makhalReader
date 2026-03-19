import { Bookmark } from 'lucide-react'
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'

interface CategoryTabsProps {
  feeds: Feed[]
}

export function CategoryTabs({ feeds }: CategoryTabsProps) {
  const { filter, setFilter, articles } = useArticlesStore()

  const categories = ['All', ...Array.from(new Set(feeds.map(f => f.category))).sort()]
  const activeCategory = filter.bookmarked ? 'Bookmarks' : (filter.category ?? 'All')

  // Compute unread counts per category from currently loaded articles.
  // Only shown in unread/all modes (not when already filtering to read-only).
  const feedNameToCategory = new Map(feeds.map(f => [f.name, f.category]))
  const categoryCounts = new Map<string, number>()
  let bookmarkCount = 0
  for (const a of articles) {
    if (filter.status === 'read') continue  // counts not meaningful in read mode
    if (a.bookmarked) bookmarkCount++
    const cat = feedNameToCategory.get(a.feed_name)
    if (cat) categoryCounts.set(cat, (categoryCounts.get(cat) ?? 0) + 1)
  }
  const totalCount = [...categoryCounts.values()].reduce((s, n) => s + n, 0)

  const handleCategoryClick = (cat: string) => {
    if (cat === 'Bookmarks') {
      setFilter({ bookmarked: true, category: null })
    } else if (cat === 'All') {
      setFilter({ bookmarked: false, category: null })
    } else {
      setFilter({ bookmarked: false, category: cat })
    }
  }

  return (
    <div className="flex items-center gap-1 px-3 py-2 overflow-x-auto scrollbar-hide border-b border-border-subtle">
      {categories.map(cat => {
        const count = cat === 'All' ? totalCount : (categoryCounts.get(cat) ?? 0)
        const isActive = activeCategory === cat
        return (
          <button
            key={cat}
            onClick={() => handleCategoryClick(cat)}
            className={`
              flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap
              ${isActive
                ? 'bg-accent-blue text-white'
                : 'bg-bg-elevated text-text-secondary hover:bg-bg-hover hover:text-text-primary'
              }
            `}
          >
            {cat}
            {count > 0 && filter.status !== 'read' && (
              <span className={`
                text-[10px] font-semibold tabular-nums leading-none px-1 py-0.5 rounded-full min-w-[16px] text-center
                ${isActive ? 'bg-white/25 text-white' : 'bg-bg-surface text-text-muted'}
              `}>
                {count > 99 ? '99+' : count}
              </span>
            )}
          </button>
        )
      })}
      <button
        onClick={() => handleCategoryClick('Bookmarks')}
        className={`
          flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap
          ${activeCategory === 'Bookmarks'
            ? 'bg-accent-blue text-white'
            : 'bg-bg-elevated text-text-secondary hover:bg-bg-hover hover:text-text-primary'
          }
        `}
      >
        <Bookmark className="w-3 h-3" />
        Bookmarks
        {bookmarkCount > 0 && (
          <span className={`
            text-[10px] font-semibold tabular-nums leading-none px-1 py-0.5 rounded-full min-w-[16px] text-center
            ${activeCategory === 'Bookmarks' ? 'bg-white/25 text-white' : 'bg-bg-surface text-text-muted'}
          `}>
            {bookmarkCount > 99 ? '99+' : bookmarkCount}
          </span>
        )}
      </button>
    </div>
  )
}
