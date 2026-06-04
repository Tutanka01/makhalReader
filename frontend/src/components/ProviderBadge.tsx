import { PROVIDER_LABELS } from '../types'

const PROVIDER_COLORS: Record<string, string> = {
  rss: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  openalex: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  crossref: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  arxiv: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  doaj: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  hal: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  dblp: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  openreview: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
}

interface ProviderBadgeProps {
  provider: string
  className?: string
}

export function ProviderBadge({ provider, className = '' }: ProviderBadgeProps) {
  const label = PROVIDER_LABELS[provider] || provider
  const colorClass = PROVIDER_COLORS[provider] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium leading-tight ${colorClass} ${className}`}>
      {label}
    </span>
  )
}
