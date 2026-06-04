import { useState } from 'react'
import type { FacetDimension, FacetSchema } from '../types'

interface FacetSchemaEditorProps {
  value: FacetSchema
  onChange: (updated: FacetSchema) => void
}

function DimensionEditor({
  dim,
  index,
  onChange,
  onRemove,
}: {
  dim: FacetDimension
  index: number
  onChange: (index: number, updated: FacetDimension) => void
  onRemove: (index: number) => void
}) {
  const [valueInput, setValueInput] = useState('')

  const addValue = () => {
    const v = valueInput.trim()
    if (!v) return
    onChange(index, { ...dim, values: [...dim.values, v] })
    setValueInput('')
  }

  const removeValue = (vi: number) => {
    onChange(index, { ...dim, values: dim.values.filter((_, i) => i !== vi) })
  }

  return (
    <div className="border border-border-subtle rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <input
          className="flex-1 px-3 py-1.5 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
          value={dim.label}
          onChange={e => onChange(index, { ...dim, label: e.target.value })}
          placeholder="Dimension label"
        />
        <select
          className="px-3 py-1.5 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm focus:outline-none focus:border-accent"
          value={dim.type}
          onChange={e => onChange(index, { ...dim, type: e.target.value })}
        >
          <option value="enum">enum</option>
          <option value="range">range</option>
        </select>
        <button
          onClick={() => onRemove(index)}
          className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full hover:bg-bg-hover text-text-muted hover:text-danger transition-colors"
          title="Remove dimension"
        >
          ×
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {dim.values.map((v, vi) => (
          <span key={vi} className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-accent/10 text-accent text-xs font-medium">
            {v}
            <button onClick={() => removeValue(vi)} className="hover:text-danger leading-none">&times;</button>
          </span>
        ))}
        <form onSubmit={e => { e.preventDefault(); addValue() }} className="inline-flex">
          <input
            className="w-24 px-2 py-0.5 rounded-full border border-border-default bg-transparent text-xs text-text-primary placeholder:text-text-muted/60 focus:outline-none"
            value={valueInput}
            onChange={e => setValueInput(e.target.value)}
            placeholder="Add value"
          />
        </form>
      </div>
    </div>
  )
}

export default function FacetSchemaEditor({ value, onChange }: FacetSchemaEditorProps) {
  const updateDimension = (index: number, updated: FacetDimension) => {
    const dims = [...value.dimensions]
    dims[index] = updated
    onChange({ ...value, dimensions: dims })
  }

  const removeDimension = (index: number) => {
    onChange({ ...value, dimensions: value.dimensions.filter((_, i) => i !== index) })
  }

  const addDimension = () => {
    const newDim: FacetDimension = {
      id: `dim_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      label: '',
      type: 'enum',
      values: [],
    }
    onChange({ ...value, dimensions: [...value.dimensions, newDim] })
  }

  return (
    <div className="space-y-2">
      {value.dimensions.map((dim, i) => (
        <DimensionEditor
          key={dim.id}
          dim={dim}
          index={i}
          onChange={updateDimension}
          onRemove={removeDimension}
        />
      ))}
      <button
        onClick={addDimension}
        className="text-xs text-accent hover:text-accent/80 font-medium transition-colors"
      >
        + Add facet dimension
      </button>
    </div>
  )
}
