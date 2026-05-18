import { ReactNode, useEffect } from 'react'
import { X } from 'lucide-react'

interface SlidePanelProps {
  open: boolean
  onClose: () => void
  width?: number
  title: string
  children: ReactNode
}

export function SlidePanel({ open, onClose, width = 510, title, children }: SlidePanelProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose()
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [open, onClose])

  if (!open) return null

  return (
    <div 
      className="fixed inset-0 z-50 flex justify-end bg-black/20"
      style={{ animation: 'fade-in 0.15s ease-out' }}
      onClick={onClose}
    >
      <div 
        className="h-screen bg-bg-base border-l border-border-subtle flex flex-col overflow-y-auto"
        style={{ 
          width: `${width}px`, 
          maxWidth: '90vw',
          animation: 'slide-in-right 0.2s ease-out' 
        }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center px-6 py-4.5 border-b border-border-subtle min-h-[73px]">
          <h2 className="text-lg font-semibold text-text-primary tracking-tight m-0">{title}</h2>
          <button 
            onClick={onClose}
            className="ml-auto p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </div>
        <div className="flex-1 p-6">
          {children}
        </div>
      </div>
    </div>
  )
}
