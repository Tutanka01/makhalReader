import { Loader2, Sparkles } from 'lucide-react'
import { useBriefingHistory } from '../../hooks/useBriefingHistory'
import { BriefingTimelineList } from './BriefingTimelineList'
import { BriefingContentPane } from './BriefingContentPane'

interface Props {
  onOpen: (id: number) => void
}

export function BriefingArchive({ onOpen }: Props) {
  const {
    summaries,
    summariesStatus,
    hasMore,
    loadingMore,
    loadMore,
    selectedId,
    detail,
    detailStatus,
    selectBriefing,
  } = useBriefingHistory()

  return (
    <div className="flex-1 overflow-hidden">
      {/* Desktop: master-detail split */}
      <div className="hidden h-full lg:grid lg:grid-cols-[340px_1fr]">
        <BriefingTimelineList
          summaries={summaries}
          summariesStatus={summariesStatus}
          hasMore={hasMore}
          loadingMore={loadingMore}
          onLoadMore={loadMore}
          selectedId={selectedId}
          onSelect={selectBriefing}
        />
        <div className="h-full overflow-y-auto">
          <div className="mx-auto w-full max-w-[820px] px-6 py-7 lg:px-8">
            <DetailPane detailStatus={detailStatus} detail={detail} selectedId={selectedId} onOpen={onOpen} />
          </div>
        </div>
      </div>

      {/* Mobile: list → detail, single column */}
      <div className="flex h-full lg:hidden">
        {selectedId === null ? (
          <BriefingTimelineList
            summaries={summaries}
            summariesStatus={summariesStatus}
            hasMore={hasMore}
            loadingMore={loadingMore}
            onLoadMore={loadMore}
            selectedId={selectedId}
            onSelect={selectBriefing}
          />
        ) : (
          <div className="h-full w-full overflow-y-auto">
            <div className="px-4 py-5">
              <DetailPane
                detailStatus={detailStatus}
                detail={detail}
                selectedId={selectedId}
                onOpen={onOpen}
                onBackToList={() => selectBriefing(null)}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function DetailPane({
  detailStatus,
  detail,
  selectedId,
  onOpen,
  onBackToList,
}: {
  detailStatus: 'idle' | 'loading' | 'ready' | 'error'
  detail: ReturnType<typeof useBriefingHistory>['detail']
  selectedId: number | null
  onOpen: (id: number) => void
  onBackToList?: () => void
}) {
  if (selectedId === null) {
    return (
      <div className="flex h-full min-h-[60vh] flex-col items-center justify-center text-center">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-bg-surface text-accent-blue">
          <Sparkles className="h-4 w-4" />
        </div>
        <p className="text-xs leading-relaxed text-text-muted">
          Choisis un briefing dans l'historique pour le relire.
        </p>
      </div>
    )
  }

  if (detailStatus === 'loading' || (detailStatus === 'idle' && !detail)) {
    return (
      <div className="flex h-full min-h-[40vh] items-center justify-center text-text-muted">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    )
  }

  if (detailStatus === 'error' || !detail) {
    return (
      <p className="px-1 py-16 text-center text-xs text-text-muted">
        Impossible de charger ce briefing.
      </p>
    )
  }

  return <BriefingContentPane briefing={detail} onOpen={onOpen} onBackToList={onBackToList} />
}
