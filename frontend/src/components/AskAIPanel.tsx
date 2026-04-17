import { useEffect, useRef, useState } from 'react'
import { Send, X, Bot, Sparkles } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

interface AskAIPanelProps {
  articleId: number
  onClose: () => void
}

// ── Tiny Markdown renderer ───────────────────────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  // Split on **bold**, *italic*, `code`
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={i} className="font-semibold text-text-primary">{part.slice(2, -2)}</strong>
    if (part.startsWith('*') && part.endsWith('*'))
      return <em key={i} className="italic">{part.slice(1, -1)}</em>
    if (part.startsWith('`') && part.endsWith('`'))
      return (
        <code key={i} className="px-1 py-0.5 rounded text-[11px] text-accent-blue font-mono"
          style={{ background: '#0E1117', border: '1px solid #2A3341' }}>
          {part.slice(1, -1)}
        </code>
      )
    return part || null
  })
}

function MiniMarkdown({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/)
  const nodes: React.ReactNode[] = []

  blocks.forEach((block, bi) => {
    const lines = block.split('\n').filter(l => l.trim())
    if (!lines.length) return

    // Blockquote — lines starting with >
    if (lines.every(l => l.trimStart().startsWith('>'))) {
      nodes.push(
        <blockquote key={bi}
          className="pl-3 my-1 italic text-text-secondary text-[12px] leading-relaxed"
          style={{ borderLeft: '2px solid rgba(68,147,248,0.5)' }}>
          {renderInline(lines.map(l => l.replace(/^\s*>\s?/, '')).join(' '))}
        </blockquote>
      )
      return
    }

    // Unordered list
    if (lines.every(l => /^[-*•]\s/.test(l.trimStart()))) {
      nodes.push(
        <ul key={bi} className="space-y-1 my-0.5">
          {lines.map((l, li) => (
            <li key={li} className="flex gap-1.5 items-start leading-relaxed">
              <span className="flex-shrink-0 mt-0.5 text-[10px]" style={{ color: 'rgba(68,147,248,0.8)' }}>●</span>
              <span>{renderInline(l.replace(/^[-*•]\s+/, ''))}</span>
            </li>
          ))}
        </ul>
      )
      return
    }

    // Ordered list
    if (lines.every(l => /^\d+[.)]\s/.test(l.trimStart()))) {
      nodes.push(
        <ol key={bi} className="space-y-1 my-0.5">
          {lines.map((l, li) => (
            <li key={li} className="flex gap-1.5 items-start leading-relaxed">
              <span className="flex-shrink-0 tabular-nums text-[11px] font-semibold" style={{ color: 'rgba(68,147,248,0.8)' }}>{li + 1}.</span>
              <span>{renderInline(l.replace(/^\d+[.)]\s+/, ''))}</span>
            </li>
          ))}
        </ol>
      )
      return
    }

    // Paragraph
    nodes.push(
      <p key={bi} className="leading-relaxed">
        {renderInline(lines.join(' '))}
      </p>
    )
  })

  return <div className="space-y-2 text-[13px] text-text-primary">{nodes}</div>
}

// ── Component ────────────────────────────────────────────────────────────────

export function AskAIPanel({ articleId, onClose }: AskAIPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [visible, setVisible] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Entrance animation
  useEffect(() => {
    const t = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(t)
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { e.stopPropagation(); onClose() }
    }
    document.addEventListener('keydown', onKey, true)
    inputRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey, true)
  }, [onClose])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const submit = async () => {
    const q = input.trim()
    if (!q || loading) return

    setInput('')
    setError(null)
    const userMsg: Message = { role: 'user', content: q }
    setMessages(prev => [...prev, userMsg])

    const assistantMsg: Message = { role: 'assistant', content: '', streaming: true }
    setMessages(prev => [...prev, assistantMsg])
    setLoading(true)

    try {
      const res = await fetch(`/api/articles/${articleId}/ask`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          try {
            const parsed = JSON.parse(data)
            if (parsed.done) break
            if (parsed.error) { setError(parsed.error); break }
            if (parsed.text) {
              accumulated += parsed.text
              setMessages(prev => {
                const copy = [...prev]
                copy[copy.length - 1] = { role: 'assistant', content: accumulated, streaming: true }
                return copy
              })
            }
          } catch { /* ignore */ }
        }
      }

      setMessages(prev => {
        const copy = [...prev]
        copy[copy.length - 1] = { role: 'assistant', content: accumulated || '(pas de réponse)', streaming: false }
        return copy
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur inconnue')
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
    if (e.key === 'Escape') { e.stopPropagation(); onClose() }
  }

  return (
    <div
      className="fixed z-[55] bottom-6 right-6 flex flex-col rounded-2xl shadow-2xl overflow-hidden"
      style={{
        width: 'min(440px, calc(100vw - 2rem))',
        height: 'min(540px, calc(100vh - 5rem))',
        background: '#161B22',
        border: '1px solid #2A3341',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(14px)',
        transition: 'opacity 0.2s ease, transform 0.2s ease',
      }}
      onClick={e => e.stopPropagation()}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ background: '#1E2430', borderBottom: '1px solid #2A3341' }}
      >
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: 'rgba(68,147,248,0.15)', border: '1px solid rgba(68,147,248,0.2)' }}>
            <Bot className="w-4 h-4" style={{ color: '#4493F8' }} />
          </div>
          <div>
            <p className="text-xs font-semibold text-text-primary leading-tight">Ask AI</p>
            <p className="text-[10px] text-text-muted leading-tight">Questions sur cet article</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg transition-colors text-text-muted hover:text-text-secondary"
          style={{ background: 'transparent' }}
          onMouseEnter={e => (e.currentTarget.style.background = '#232B39')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 pb-4">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
              style={{ background: 'rgba(68,147,248,0.08)', border: '1px solid rgba(68,147,248,0.15)' }}>
              <Sparkles className="w-5 h-5" style={{ color: '#4493F8' }} />
            </div>
            <div>
              <p className="text-sm font-medium text-text-secondary">Posez une question</p>
              <p className="text-xs text-text-muted mt-1 max-w-[210px] leading-relaxed">
                L'IA répond uniquement à partir du contenu de cet article.
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5 justify-center mt-1">
              {['Quelle est la conclusion ?', 'Résume en quelques points', 'Quels sont les arguments clés ?'].map(q => (
                <button
                  key={q}
                  onClick={() => { setInput(q); inputRef.current?.focus() }}
                  className="text-[11px] px-2.5 py-1 rounded-full text-text-muted hover:text-text-secondary transition-colors"
                  style={{ background: '#1E2430', border: '1px solid #2A3341' }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
            {msg.role === 'assistant' && (
              <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
                style={{ background: 'rgba(68,147,248,0.15)' }}>
                <Bot className="w-3.5 h-3.5" style={{ color: '#4493F8' }} />
              </div>
            )}

            <div
              className={`max-w-[80%] px-3 py-2.5 rounded-2xl ${
                msg.role === 'user' ? 'rounded-tr-sm' : 'rounded-tl-sm'
              }`}
              style={
                msg.role === 'user'
                  ? { background: '#4493F8', color: '#fff' }
                  : { background: '#1E2430', border: '1px solid #2A3341' }
              }
            >
              {msg.role === 'user' ? (
                <p className="text-sm leading-relaxed">{msg.content}</p>
              ) : (
                <>
                  <MiniMarkdown text={msg.content || ' '} />
                  {msg.streaming && (
                    <span
                      className="inline-block w-1 h-3.5 rounded-sm align-middle animate-pulse ml-0.5"
                      style={{ background: '#4493F8', verticalAlign: 'text-bottom' }}
                    />
                  )}
                </>
              )}
            </div>
          </div>
        ))}

        {error && (
          <div className="text-xs rounded-xl px-3 py-2"
            style={{ background: 'rgba(248,81,73,0.1)', border: '1px solid rgba(248,81,73,0.2)', color: '#F85149' }}>
            ⚠ {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="px-3 pb-3 pt-2 flex-shrink-0" style={{ borderTop: '1px solid #2A3341' }}>
        <div className="flex items-end gap-2 rounded-xl px-3 py-2"
          style={{ background: '#1E2430', border: '1px solid #2A3341' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ex : Quelle est la conclusion ?"
            disabled={loading}
            rows={1}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted resize-none focus:outline-none disabled:opacity-50 leading-5"
            style={{ maxHeight: 80, overflowY: 'auto' }}
          />
          <button
            onClick={submit}
            disabled={!input.trim() || loading}
            className="p-2 rounded-lg transition-all duration-150 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: input.trim() && !loading ? '#4493F8' : 'rgba(68,147,248,0.15)' }}
            title="Envoyer (Entrée)"
          >
            <Send className="w-3.5 h-3.5 text-white" />
          </button>
        </div>
        <p className="text-[10px] text-text-muted mt-1.5 text-center">Entrée pour envoyer · Échap pour fermer</p>
      </div>
    </div>
  )
}
