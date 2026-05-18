import { Bookmark } from 'lucide-react'
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'

interface CategoryTabsProps {
  feeds: Feed[]
}

export function CategoryTabs({ feeds }: CategoryTabsProps) {
  // Deprecated in favor of Sidebar
  return null
}
