export function BriefingSkeleton() {
  return (
    <div className="space-y-6" aria-hidden>
      <div className="briefing-shimmer h-8 w-2/3 rounded-lg" />
      <div className="briefing-shimmer h-20 w-full rounded-lg" />
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map(i => <div key={i} className="briefing-shimmer h-24 rounded-xl" />)}
      </div>
      {[0, 1].map(i => (
        <div key={i} className="space-y-2">
          <div className="briefing-shimmer h-6 w-1/3 rounded" />
          <div className="briefing-shimmer h-16 w-full rounded" />
        </div>
      ))}
    </div>
  )
}
