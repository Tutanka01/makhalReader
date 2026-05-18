import { useEffect, useRef, useState } from 'react'
import { X, Plus, Trash2, Loader2, UserCircle2 } from 'lucide-react'
import type { ProfileKind, ResearchProfileEntry } from '../types'
import { useResearchStore } from '../store/research'

interface Props {
  open: boolean
  onClose: () => void
}

const KIND_CONFIG: { kind: ProfileKind; label: string; color: string; hint: string }[] = [
  {
    kind: 'topic',
    label: 'Topics',
    color: 'bg-accent/20 text-accent',
    hint: 'e.g. requirements engineering, LLMs, NLP',
  },
  {
    kind: 'method',
    label: 'Methods',
    color: 'bg-purple/20 text-purple',
    hint: 'e.g. grounded theory, systematic review, RCT',
  },
  {
    kind: 'domain',
    label: 'Domains',
    color: 'bg-success/20 text-success',
    hint: 'e.g. software engineering, medicine, education',
  },
  {
    kind: 'avoid',
    label: 'Avoid',
    color: 'bg-danger/20 text-danger',
    hint: 'e.g. blockchain, marketing, cryptocurrency',
  },
]

function WeightSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <input
      type="range"
      min={0.1}
      max={2.0}
      step={0.1}
      value={value}
      onChange={(e) => onChange(parseFloat(e.target.value))}
      className="w-20 h-1.5 accent-accent cursor-pointer"
      title={`Weight: ${value.toFixed(1)}`}
    />
  )
}

function EntryRow({
  entry,
  colorClass,
  onChange,
  onDelete,
}: {
  entry: ResearchProfileEntry
  colorClass: string
  onChange: (e: ResearchProfileEntry) => void
  onDelete: () => void
}) {
  return (
    <div className="flex items-center gap-2 py-1">
      <span
        className={`px-2 py-0.5 rounded text-xs font-medium truncate max-w-[9rem] ${colorClass}`}
        title={entry.label}
      >
        {entry.label}
      </span>
      {entry.source === 'feedback' && (
        <span className="text-[10px] text-text-muted italic flex-shrink-0">auto</span>
      )}
      <WeightSlider
        value={entry.weight}
        onChange={(w) => onChange({ ...entry, weight: w })}
      />
      <span className="text-[11px] text-text-muted w-6 flex-shrink-0">
        {entry.weight.toFixed(1)}
      </span>
      <button
        onClick={onDelete}
        className="ml-auto text-text-muted hover:text-danger flex-shrink-0"
        title="Remove"
      >
        <Trash2 size={13} />
      </button>
    </div>
  )
}

function AddTagInput({
  kind,
  onAdd,
}: {
  kind: ProfileKind
  onAdd: (label: string) => void
}) {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const commit = () => {
    const trimmed = value.trim().toLowerCase()
    if (trimmed) {
      onAdd(trimmed)
      setValue('')
      inputRef.current?.focus()
    }
  }

  return (
    <div className="flex gap-1.5 mt-1.5">
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
        }}
        placeholder="Add tag…"
        className="flex-1 text-xs rounded border border-border-default bg-bg-base px-2 py-1 outline-none focus:ring-1 focus:ring-accent"
      />
      <button
        onClick={commit}
        disabled={!value.trim()}
        className="text-accent hover:text-accent/80 disabled:opacity-30"
        title={`Add ${kind}`}
      >
        <Plus size={15} />
      </button>
    </div>
  )
}

export default function ResearchProfileEditor({ open, onClose }: Props) {
  const { profile, profileLoading, profileError, fetchProfile, saveProfile } =
    useResearchStore()

  // Local draft — edits are not saved until the user clicks Save
  const [draft, setDraft] = useState<ResearchProfileEntry[]>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  // Load profile when panel opens
  useEffect(() => {
    if (open) {
      fetchProfile()
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync draft when remote profile arrives (don't overwrite mid-edit)
  useEffect(() => {
    if (profile !== null && !dirty) {
      setDraft(profile)
    }
  }, [profile]) // eslint-disable-line react-hooks/exhaustive-deps

  const updateEntry = (idx: number, updated: ResearchProfileEntry) => {
    setDraft((d) => d.map((e, i) => (i === idx ? updated : e)))
    setDirty(true)
  }

  const deleteEntry = (idx: number) => {
    setDraft((d) => d.filter((_, i) => i !== idx))
    setDirty(true)
  }

  const addEntry = (kind: ProfileKind, label: string) => {
    // Avoid duplicates within the draft
    const already = draft.some((e) => e.kind === kind && e.label === label)
    if (already) return
    setDraft((d) => [...d, { kind, label, weight: 1.0, source: 'manual' }])
    setDirty(true)
  }

  const handleSave = async () => {
    setSaving(true)
    // Mark deleted entries with weight=0 so the backend removes them
    const toSend = draft.map((e) => ({ ...e }))
    await saveProfile(toSend)
    setSaving(false)
    setDirty(false)
  }

  const handleDiscard = () => {
    if (profile !== null) setDraft(profile)
    setDirty(false)
  }

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <aside className="fixed right-0 top-0 h-full w-96 max-w-full bg-bg-surface shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border-subtle">
          <UserCircle2 size={18} className="text-accent" />
          <h2 className="font-semibold text-sm text-text-primary flex-1">
            Research Profile
          </h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">
          {profileLoading && !draft.length && (
            <div className="flex justify-center pt-10 text-text-muted">
              <Loader2 size={22} className="animate-spin" />
            </div>
          )}
          {profileError && (
            <p className="text-xs text-danger">{profileError}</p>
          )}

          {KIND_CONFIG.map(({ kind, label, color, hint }) => {
            const entries = draft
              .map((e, idx) => ({ e, idx }))
              .filter(({ e }) => e.kind === kind)

            return (
              <section key={kind}>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary mb-1">
                  {label}
                </h3>
                <p className="text-[10px] text-text-muted mb-2 italic">{hint}</p>

                {entries.length === 0 && (
                  <p className="text-xs text-text-muted italic">None yet</p>
                )}
                {entries.map(({ e, idx }) => (
                  <EntryRow
                    key={`${kind}-${e.label}`}
                    entry={e}
                    colorClass={color}
                    onChange={(updated) => updateEntry(idx, updated)}
                    onDelete={() => deleteEntry(idx)}
                  />
                ))}

                <AddTagInput kind={kind} onAdd={(lbl) => addEntry(kind, lbl)} />
              </section>
            )
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 px-4 py-3 border-t border-border-subtle">
          {dirty && (
            <button
              onClick={handleDiscard}
              className="text-xs text-text-muted hover:text-text-secondary"
            >
              Discard
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="ml-auto flex items-center gap-1.5 rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving && <Loader2 size={12} className="animate-spin" />}
            Save profile
          </button>
        </div>
      </aside>
    </>
  )
}
