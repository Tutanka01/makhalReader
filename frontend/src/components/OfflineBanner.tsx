import { WifiOff } from 'lucide-react'

export function OfflineBanner({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div role="status" className="fixed inset-x-0 bottom-0 z-50 flex items-center justify-center gap-2 border-t border-accent-yellow/30 bg-bg-surface/95 px-4 pt-2.5 pb-[max(0.625rem,env(safe-area-inset-bottom))] backdrop-blur-sm">
      <WifiOff className="w-3.5 h-3.5 text-accent-yellow flex-shrink-0" />
      <span className="text-xs text-accent-yellow font-medium">
        Hors ligne — contenu mis en cache affiché
      </span>
    </div>
  )
}
