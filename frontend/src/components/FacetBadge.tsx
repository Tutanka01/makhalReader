import type { FacetSchema, FacetValue } from '../types'

interface FacetBadgeProps {
  facetsJson: string | null | undefined
  schema: FacetSchema | null | undefined
}

export function FacetBadge({ facetsJson, schema }: FacetBadgeProps) {
  if (!facetsJson || !schema) return null
  let facets: FacetValue[]
  try {
    facets = JSON.parse(facetsJson)
  } catch {
    return null
  }
  return (
    <>
      {facets.map(fv => {
        const dim = schema.dimensions.find(d => d.id === fv.dimensionId)
        if (!dim) return null
        return (
          <span
            key={fv.dimensionId}
            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-800"
          >
            {dim.label}: {fv.value}
          </span>
        )
      })}
    </>
  )
}
