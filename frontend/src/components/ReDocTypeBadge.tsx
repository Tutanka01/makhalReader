import { FacetBadge } from './FacetBadge'
import type { FacetSchema } from '../types'

const CS_RE_SCHEMA: FacetSchema = {
  version: 1,
  dimensions: [{
    id: 're_document_type',
    label: 'RE',
    type: 'enum',
    values: ['elicitation', 'extraction', 'method'],
  }],
}

interface ReDocTypeBadgeProps {
  type: string | null | undefined
  className?: string
}

export function ReDocTypeBadge({ type, className = '' }: ReDocTypeBadgeProps) {
  if (!type) return null
  const facetsJson = JSON.stringify([{ dimensionId: 're_document_type', value: type }])
  return (
    <span className={className}>
      <FacetBadge facetsJson={facetsJson} schema={CS_RE_SCHEMA} />
    </span>
  )
}
