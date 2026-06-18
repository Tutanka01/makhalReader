import { useCallback, useEffect, useState } from 'react'
import type { Briefing } from '../types'

type Status = 'loading' | 'ready' | 'empty' | 'generating' | 'error'

export function useBriefing() {
  const [briefing, setBriefing] = useState<Briefing | null>(null)
  const [status, setStatus] = useState<Status>('loading')

  const reload = useCallback(async () => {
    try {
      const res = await fetch('/api/briefings/latest', { credentials: 'include' })
      if (res.status === 404) { setBriefing(null); setStatus('empty'); return }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setBriefing(await res.json())
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [])

  const generate = useCallback(async () => {
    setStatus('generating')
    try {
      const res = await fetch('/api/briefings/generate?hours=24', { method: 'POST', credentials: 'include' })
      if (res.status === 404) { setBriefing(null); setStatus('empty'); return }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setBriefing(await res.json())
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  useEffect(() => {
    const onReady = () => { reload() }
    window.addEventListener('makhal:briefing-ready', onReady)
    return () => window.removeEventListener('makhal:briefing-ready', onReady)
  }, [reload])

  return { briefing, status, generate, reload }
}
