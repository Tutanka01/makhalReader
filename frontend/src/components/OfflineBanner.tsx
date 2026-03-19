import { WifiOff } from 'lucide-react'

export function OfflineBanner({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div className="fixed bottom-0 inset-x-0 z-50 flex items-center justify-center gap-2 px-4 py-2.5 bg-accent-yellow/10 border-t border-accent-yellow/30 backdrop-blur-sm">
      <WifiOff className="w-3.5 h-3.5 text-accent-yellow flex-shrink-0" />
      <span className="text-xs text-accent-yellow font-medium">
        Hors ligne — contenu mis en cache affiché
      </span>
    </div>
  )
}
