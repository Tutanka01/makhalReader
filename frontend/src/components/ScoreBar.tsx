interface ScoreBarProps {
  score: number | null
}

export function ScoreBar({ score }: ScoreBarProps) {
  if (score === null || score === undefined) {
    return (
      <div className="flex items-center gap-2 mb-2">
        <div className="h-1 flex-1 rounded-full bg-bg-elevated overflow-hidden">
          <div className="h-full w-0 rounded-full" />
        </div>
        <span className="text-xs font-medium text-text-muted w-6 text-right">–</span>
      </div>
    )
  }

  const percentage = Math.max(0, Math.min(100, (score / 10) * 100))

  let barColor: string
  let textColor: string
  if (score >= 8) {
    barColor = 'var(--color-score-high)'
    textColor = 'var(--color-score-high)'
  } else if (score >= 5) {
    barColor = 'var(--color-score-mid)'
    textColor = 'var(--color-score-mid)'
  } else {
    barColor = 'var(--color-score-low)'
    textColor = 'var(--color-score-low)'
  }

  return (
    <div className="flex items-center gap-2 mb-2">
      <div className="h-1 flex-1 rounded-full bg-bg-elevated overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${percentage}%`, backgroundColor: barColor }}
        />
      </div>
      <span
        className="text-xs font-semibold w-6 text-right tabular-nums"
        style={{ color: textColor }}
      >
        {score.toFixed(1)}
      </span>
    </div>
  )
}
