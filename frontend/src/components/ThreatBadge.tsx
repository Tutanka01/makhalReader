import { useState, useRef, useEffect } from 'react'

interface ThreatBadgeProps {
  overlap: number
  positioningNote?: string | null
}

export function ThreatBadge({ overlap, positioningNote }: ThreatBadgeProps) {
  const [showTooltip, setShowTooltip] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  if (overlap < 0.6) return null

  const handleMouseEnter = () => {
    clearTimeout(timerRef.current)
    setShowTooltip(true)
  }

  const handleMouseLeave = () => {
    timerRef.current = setTimeout(() => setShowTooltip(false), 200)
  }

  useEffect(() => {
    return () => clearTimeout(timerRef.current)
  }, [])

  const pct = Math.round(overlap * 100)

  return (
    <span
      className="inline-flex items-center px-1.5 py-[1px] rounded-[4px] text-[10px] font-medium tracking-wide bg-danger-bg text-danger cursor-help relative"
      title={`${pct}% overlap`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      ⚠ {pct}% overlap
      {showTooltip && positioningNote && (
        <span
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 bg-gray-900 text-white text-[11px] leading-snug rounded shadow-lg whitespace-normal max-w-[220px] z-50"
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {positioningNote}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
        </span>
      )}
    </span>
  )
}
