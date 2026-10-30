import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { IconButton, Kbd } from './ui'

const GROUPS: Array<{ title: string; items: Array<[string[], string]> }> = [
  {
    title: 'Lecture',
    items: [
      [['j'], 'Article suivant'],
      [['k'], 'Article précédent'],
      [['r'], 'Marquer lu / non lu'],
      [['b'], 'Ajouter / retirer des favoris'],
      [['o'], 'Ouvrir l’original'],
    ],
  },
  {
    title: 'Navigation',
    items: [
      [['/'], 'Rechercher'],
      [['['], 'Afficher / masquer la liste'],
      [['Échap'], 'Fermer'],
      [['?'], 'Afficher cette aide'],
    ],
  },
]

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
  }, [])

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--color-overlay)' }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        className="animate-pop-in w-full max-w-sm rounded-xl border border-border-default bg-bg-surface p-5 shadow-elevated"
        onClick={e => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="shortcuts-title" className="text-sm font-semibold text-text-primary">
            Raccourcis clavier
          </h2>
          <IconButton ref={closeRef} onClick={onClose} icon={X} label="Fermer" />
        </div>

        <div className="space-y-5">
          {GROUPS.map(group => (
            <section key={group.title}>
              <h3 className="mb-2 text-xs font-medium text-text-muted">{group.title}</h3>
              <ul className="space-y-1.5">
                {group.items.map(([keys, label]) => (
                  <li key={label} className="flex items-center justify-between gap-4 text-sm text-text-secondary">
                    <span>{label}</span>
                    <span className="flex gap-1">
                      {keys.map(k => <Kbd key={k}>{k}</Kbd>)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        <p className="mt-5 border-t border-border-subtle pt-4 text-xs leading-relaxed text-text-muted">
          Sur iPad et mobile : glisse une carte vers la gauche pour la marquer lue, vers la droite pour l’ajouter aux favoris.
        </p>
      </div>
    </div>
  )
}
