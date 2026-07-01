export function BriefingSkeleton() {
  return (
    <div className="space-y-5" aria-hidden>
      <div className="space-y-3 border-b border-border-subtle pb-5">
        <div className="briefing-shimmer h-4 w-44 rounded-md" />
        <div className="briefing-shimmer h-9 w-48 rounded-md" />
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="briefing-shimmer h-24 rounded-md" />
        <div className="grid grid-cols-2 gap-2">
          {[0, 1, 2, 3].map(i => <div key={i} className="briefing-shimmer h-14 rounded-md" />)}
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {[0, 1].map(i => <div key={i} className="briefing-shimmer h-28 rounded-md" />)}
      </div>
      {[0, 1].map(i => (
        <div key={i} className="space-y-3 rounded-md bg-bg-surface p-4">
          <div className="briefing-shimmer h-6 w-1/2 rounded-md" />
          <div className="briefing-shimmer h-16 w-full rounded-md" />
          <div className="briefing-shimmer h-12 w-full rounded-md" />
        </div>
      ))}
    </div>
  )
}
