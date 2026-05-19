import { useState, useEffect, useCallback } from 'react'
import { AlertTriangle, RefreshCw, Save, ExternalLink } from 'lucide-react'
import type { NoveltyAlert, ThreatScanResponse, ThesisContribution } from '../types'

interface ThreatViewProps {
  onSelectArticle?: (id: number) => void
}

export default function ThreatView({ onSelectArticle }: ThreatViewProps) {
  const [alerts, setAlerts] = useState<NoveltyAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<ThreatScanResponse | null>(null)
  const [contribution, setContribution] = useState<ThesisContribution | null>(null)
  const [statement, setStatement] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch('/api/research/threats?since_days=30&min_overlap=0.0', { credentials: 'include' })
      if (res.ok) {
        const data: NoveltyAlert[] = await res.json()
        setAlerts(data)
      }
    } catch (e) {
      console.error('Failed to fetch threats', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchContribution = useCallback(async () => {
    try {
      const res = await fetch('/api/research/profile/contribution', { credentials: 'include' })
      if (res.ok) {
        const data: ThesisContribution | null = await res.json()
        if (data) {
          setContribution(data)
          setStatement(data.statement)
        }
      }
    } catch (e) {
      console.error('Failed to fetch contribution', e)
    }
  }, [])

  useEffect(() => {
    fetchAlerts()
    fetchContribution()
  }, [fetchAlerts, fetchContribution])

  const handleScan = async () => {
    setScanning(true)
    setScanResult(null)
    try {
      const res = await fetch('/api/research/threats/scan?window_days=14', {
        method: 'POST',
        credentials: 'include',
      })
      if (res.ok) {
        const data: ThreatScanResponse = await res.json()
        setScanResult(data)
        fetchAlerts()
      } else if (res.status === 400) {
        const err = await res.json()
        alert(err.detail || 'Scan failed')
      }
    } catch (e) {
      console.error('Scan failed', e)
    } finally {
      setScanning(false)
    }
  }

  const handleSaveContribution = async () => {
    if (!statement.trim()) return
    setSaving(true)
    try {
      const res = await fetch('/api/research/profile/contribution', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ statement: statement.trim() }),
      })
      if (res.ok) {
        const data: ThesisContribution = await res.json()
        setContribution(data)
      }
    } catch (e) {
      console.error('Failed to save contribution', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-lg font-semibold text-text-primary mb-1 flex items-center gap-2">
          <AlertTriangle size={18} className="text-danger" />
          Novelty Threat Monitor
        </h1>
        <p className="text-sm text-text-muted mb-6">
          Automatically compare new papers against your thesis contribution and flag significant overlap.
        </p>

        {/* ── Contribution statement editor ── */}
        <div className="bg-bg-surface border border-border-default rounded-lg p-4 mb-6">
          <h2 className="text-sm font-medium text-text-primary mb-2">Thesis Contribution Statement</h2>
          <textarea
            className="w-full bg-bg-base border border-border-default rounded-md p-3 text-sm text-text-primary resize-none focus:outline-none focus:border-accent-blue"
            rows={4}
            maxLength={2000}
            placeholder="Describe your thesis contribution in 1–3 sentences…"
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
          />
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-text-muted">{statement.length}/2000</span>
            {contribution && (
              <span className="text-xs text-text-muted">
                Last updated: {new Date(contribution.updated_at).toLocaleDateString()}
              </span>
            )}
          </div>
          <button
            onClick={handleSaveContribution}
            disabled={saving || !statement.trim()}
            className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-accent-blue text-white text-xs font-medium rounded-md hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            <Save size={14} />
            {saving ? 'Saving…' : 'Save Statement'}
          </button>
        </div>

        {/* ── Scan controls ── */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-text-primary">Threat Alerts</h2>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-danger text-white text-xs font-medium rounded-md hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
            {scanning ? 'Scanning…' : 'Scan Now'}
          </button>
        </div>

        {/* ── Scan result ── */}
        {scanResult && (
          <div className="bg-success-bg border border-success text-success text-xs rounded-md px-3 py-2 mb-4">
            Scanned {scanResult.scanned} articles — {scanResult.alerts_created} new alerts, {scanResult.skipped} skipped
          </div>
        )}

        {/* ── Alerts list ── */}
        {loading ? (
          <div className="flex items-center justify-center py-12 text-text-muted text-sm">
            <RefreshCw size={16} className="animate-spin mr-2" />
            Loading threats…
          </div>
        ) : alerts.length === 0 ? (
          <div className="bg-bg-surface border border-border-default rounded-lg p-8 text-center text-text-muted text-sm">
            No threat alerts yet. Click "Scan Now" to check recent high-scored articles for thesis overlap.
          </div>
        ) : (
          <div className="space-y-2">
            {alerts.map((alert) => (
              <div
                key={alert.article_id}
                className="bg-bg-surface border border-border-default rounded-lg p-4 hover:border-border-hover transition-colors cursor-pointer"
                onClick={() => onSelectArticle?.(alert.article_id)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`inline-flex items-center px-1.5 py-[1px] rounded-[4px] text-[10px] font-bold tracking-wide ${
                          alert.overlap_score >= 0.8
                            ? 'bg-danger-bg text-danger'
                            : alert.overlap_score >= 0.6
                            ? 'bg-warning-bg text-warning'
                            : 'bg-accent-light text-accent'
                        }`}
                      >
                        {Math.round(alert.overlap_score * 100)}% overlap
                      </span>
                      {alert.score != null && (
                        <span className="text-[10px] text-text-muted font-mono">
                          Score: {alert.score.toFixed(1)}
                        </span>
                      )}
                    </div>
                    <h3 className="text-sm font-medium text-text-primary leading-snug line-clamp-2">
                      {alert.title}
                    </h3>
                    <p className="text-xs text-text-secondary mt-1 line-clamp-2">
                      {alert.positioning_note}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5 text-[11px] text-text-muted">
                      <span>Checked {new Date(alert.checked_at).toLocaleDateString()}</span>
                      <ExternalLink size={11} className="opacity-50" />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
