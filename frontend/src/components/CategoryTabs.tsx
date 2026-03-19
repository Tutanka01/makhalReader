import { Bookmark } from 'lucide-react'
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'

interface CategoryTabsProps {
  feeds: Feed[]
}

export function CategoryTabs({ feeds }: CategoryTabsProps) {
  const { filter, setFilter } = useArticlesStore()

  const categories = ['All', ...Array.from(new Set(feeds.map(f => f.category))).sort()]

  const activeCategory = filter.bookmarked ? 'Bookmarks' : (filter.category ?? 'All')

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
      {categories.map(cat => (
        <button
          key={cat}
          onClick={() => handleCategoryClick(cat)}
          className={`
            flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap
            ${activeCategory === cat
              ? 'bg-accent-blue text-white'
              : 'bg-bg-elevated text-text-secondary hover:bg-bg-hover hover:text-text-primary'
            }
          `}
        >
          {cat}
        </button>
      ))}
      <button
        onClick={() => handleCategoryClick('Bookmarks')}
        className={`
          flex-shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap
          ${activeCategory === 'Bookmarks'
            ? 'bg-accent-blue text-white'
            : 'bg-bg-elevated text-text-secondary hover:bg-bg-hover hover:text-text-primary'
          }
        `}
      >
        <Bookmark className="w-3 h-3" />
        Bookmarks
      </button>
    </div>
  )
}
