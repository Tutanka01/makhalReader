import { useState, useEffect, useRef, useCallback } from 'react'
import { FileText, ChevronDown, Copy, Check, Loader2 } from 'lucide-react'
import type { HighlightSectionCount } from '../types'
import { VALID_THESIS_SECTIONS } from '../types'

export default function WriteAssistPanel() {
  const [sections, setSections] = useState<HighlightSectionCount[]>([])
  const [selectedSection, setSelectedSection] = useState<string>('')
  const [sectionOpen, setSectionOpen] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [output, setOutput] = useState('')
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sectionRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const fetchSections = useCallback(async () => {
    try {
      const res = await fetch('/api/research/export-highlights/sections', { credentials: 'include' })
      if (res.ok) {
        const data: HighlightSectionCount[] = await res.json()
        setSections(data)
        if (data.length > 0 && !selectedSection) {
          setSelectedSection(data[0].thesis_section)
        }
      }
    } catch (e) {
      console.error('Failed to fetch sections', e)
    }
  }, [])

  useEffect(() => {
    fetchSections()
  }, [fetchSections])

  useEffect(() => {
    if (!sectionOpen) return
    function handleClick(e: MouseEvent) {
      if (sectionRef.current && !sectionRef.current.contains(e.target as Node)) {
        setSectionOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [sectionOpen])

  const handleGenerate = async () => {
    if (!selectedSection || generating) return

    setGenerating(true)
    setOutput('')
    setError(null)
    abortRef.current = new AbortController()

    try {
      const res = await fetch('/api/research/export-highlights', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thesis_section: selectedSection,
          window_days: 30,
          max_highlights: 20,
        }),
        signal: abortRef.current.signal,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        setError(err.detail || 'Generation failed')
        setGenerating(false)
        return
      }

      const reader = res.body?.getReader()
      if (!reader) { setError('No response body'); setGenerating(false); return }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (payload === '{"done": true}') break
          try {
            const parsed = JSON.parse(payload)
            if (parsed.text) {
              setOutput(prev => prev + parsed.text)
            }
            if (parsed.error) {
              setError(parsed.error)
            }
          } catch {
            // skip malformed lines
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setError(e.message || 'Generation failed')
      }
    } finally {
      setGenerating(false)
      abortRef.current = null
    }
  }

  const handleCopy = async () => {
    if (!output) return
    try {
      await navigator.clipboard.writeText(output)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }

  const sectionCount = sections.find(s => s.thesis_section === selectedSection)

  return (
    <div className="h-full flex flex-col bg-bg-base">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-default">
        <div className="flex items-center gap-2.5">
          <FileText className="w-4 h-4 text-accent" />
          <h1 className="text-sm font-semibold text-text-primary">Writing Assistant</h1>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-5 max-w-3xl mx-auto w-full">
        {/* Section selector */}
        <div className="space-y-2">
          <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
            Thesis Section
          </label>
          <div ref={sectionRef} className="relative">
            <button
              onClick={() => setSectionOpen(v => !v)}
              className="w-full flex items-center justify-between gap-2 bg-bg-surface border border-border-default rounded-lg px-3 py-2 text-sm text-text-primary hover:border-border-strong transition-colors"
            >
              <span>{selectedSection || 'Select a section…'}</span>
              <div className="flex items-center gap-2">
                {sectionCount && sectionCount.count > 0 && (
                  <span className="text-[11px] text-text-muted bg-bg-elevated rounded-full px-2 py-[1px] font-mono">
                    {sectionCount.count}
                  </span>
                )}
                <ChevronDown size={14} className={`text-text-muted transition-transform ${sectionOpen ? 'rotate-180' : ''}`} />
              </div>
            </button>
            {sectionOpen && (
              <div className="absolute left-0 right-0 mt-1 bg-bg-surface border border-border-default rounded-lg shadow-xl z-10 max-h-60 overflow-y-auto">
                {VALID_THESIS_SECTIONS.map(s => {
                  const cnt = sections.find(sc => sc.thesis_section === s)?.count ?? 0
                  return (
                    <button
                      key={s}
                      onClick={() => { setSelectedSection(s); setSectionOpen(false) }}
                      className={`w-full flex items-center justify-between text-left text-sm px-3 py-2 transition-colors ${
                        selectedSection === s ? 'bg-accent/5 text-accent font-medium' : 'text-text-secondary hover:bg-bg-hover'
                      }`}
                    >
                      <span>{s}</span>
                      <span className="text-[11px] text-text-muted font-mono">{cnt}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
          {sectionCount && sectionCount.count < 2 && selectedSection && (
            <p className="text-[11px] text-warning">
              At least 2 highlights are needed for synthesis. This section only has {sectionCount.count}.
            </p>
          )}
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={!selectedSection || generating || (sectionCount?.count ?? 0) < 2}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-accent text-white hover:bg-accent-strong active:scale-[0.98]"
        >
          {generating ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Generating…
            </>
          ) : (
            <>
              <FileText className="w-4 h-4" />
              Generate Synthesis
            </>
          )}
        </button>

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg bg-danger/5 border border-danger/20 text-xs text-danger">
            {error}
          </div>
        )}

        {/* Output */}
        {output && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
                Generated Paragraph
              </label>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 text-[11px] text-text-muted hover:text-text-secondary transition-colors px-2 py-1 rounded hover:bg-bg-hover"
              >
                {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <div className="p-4 rounded-xl bg-bg-surface border border-border-default text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
              {output}
              {generating && <span className="inline-block w-1.5 h-4 bg-accent ml-0.5 animate-pulse" />}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}