import { FacetBadge } from './FacetBadge'
import type { FacetSchema } from '../types'

const CS_CONTRIB_SCHEMA: FacetSchema = {
  version: 1,
  dimensions: [{
    id: 'contribution_type',
    label: 'Contribution',
    type: 'enum',
    values: ['method', 'survey', 'benchmark', 'empirical', 'theory', 'position', 'tool', 'incident', 'tutorial', 'news', 'other'],
  }],
}

interface ContribTypeBadgeProps {
  type: string | null | undefined
  className?: string
}

export function ContribTypeBadge({ type, className = '' }: ContribTypeBadgeProps) {
  if (!type) return null
  const facetsJson = JSON.stringify([{ dimensionId: 'contribution_type', value: type }])
  return (
    <span className={className}>
      <FacetBadge facetsJson={facetsJson} schema={CS_CONTRIB_SCHEMA} />
    </span>
  )
}
