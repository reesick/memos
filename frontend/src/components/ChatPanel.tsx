import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../types'
import { api } from '../api'

interface Props {
  sessionId: string
  onFactsAdded: (n: number) => void
  onMemoriesChanged: () => void
  onClear: () => void
}

const STARTERS = ['Got it.', 'Interesting.', 'I see.', 'Makes sense.']

export function ChatPanel({ sessionId, onFactsAdded, onMemoriesChanged, onClear }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const messagesRef = useRef<HTMLDivElement>(null)

  const scroll = () => {
    if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight
  }

  useEffect(scroll, [messages])

  function addMsg(msg: ChatMessage) {
    setMessages(prev => [...prev, msg])
  }

  async function sendMessage() {
    const text = input.trim()
    if (!text) return
    setInput('')

    addMsg({ id: crypto.randomUUID(), role: 'you', text })

    let willInject = false
    try {
      const d = await api.shouldInject(text)
      willInject = d.inject
    } catch {}

    // Add to memory
    try {
      const d = await api.addMemory(text, sessionId)
      if (d.facts_added > 0) {
        onFactsAdded(d.facts_added)
        setTimeout(onMemoriesChanged, 400)
      }
    } catch {}

    // Augment
    let augmented = text
    let injected = false
    try {
      const d = await api.augment(text, 3)
      augmented = d.augmented_prompt
      injected = d.injected
    } catch {}

    if (injected) {
      addMsg({ id: crypto.randomUUID(), role: 'ai', text: '[memory injected into context]', isContext: true })
    }

    const base = STARTERS[Math.floor(Math.random() * STARTERS.length)]
    const aiReply = (augmented !== text || willInject)
      ? `${base} I've noted that and kept it in memory.`
      : `${base} Tell me more.`
    addMsg({ id: crypto.randomUUID(), role: 'ai', text: aiReply })
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  function clearChat() {
    setMessages([])
    onClear()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--surface)', borderRight: '1px solid var(--border)', height: '100%' }}>
      {/* Header */}
      <div style={{ height: 40, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 16px', gap: 8, flexShrink: 0 }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Conversation</span>
        <div style={{ marginLeft: 'auto' }}>
          <button
            onClick={clearChat}
            style={{ fontSize: 11, fontWeight: 500, padding: '3px 10px', border: '1px solid var(--danger)', color: 'var(--danger)', background: 'transparent', borderRadius: 4, cursor: 'pointer', letterSpacing: '0.02em' }}
            onMouseEnter={e => (e.currentTarget.style.background = '#fef2f2')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >END</button>
        </div>
      </div>

      {/* Messages */}
      <div ref={messagesRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 8px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ textAlign: 'center', fontSize: 10, color: 'var(--text-muted)', margin: '12px 0 4px', fontFamily: 'var(--mono)' }}>
          {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </div>
        {messages.map(m => (
          <div key={m.id} className="fade-in" style={{ display: 'flex', flexDirection: 'column', alignItems: m.role === 'you' ? 'flex-end' : 'flex-start', marginTop: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 2 }}>
              {m.role === 'you' ? 'YOU' : (
                m.isContext
                  ? <span>AI <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', background: 'var(--accent-soft)', color: 'var(--accent)', borderRadius: 3, padding: '1px 5px', marginLeft: 6 }}>memory</span></span>
                  : 'AI'
              )}
            </div>
            <div style={{
              maxWidth: 260, padding: '7px 11px', borderRadius: 8, lineHeight: 1.5,
              fontSize: m.isContext ? 11 : 13,
              border: m.isContext ? '1px solid var(--accent)' : '1px solid var(--border)',
              background: m.isContext ? '#f0fdf4' : m.role === 'you' ? 'var(--surface-2)' : 'var(--surface)',
              color: m.isContext ? 'var(--accent)' : 'var(--text-primary)',
              fontFamily: m.isContext ? 'var(--mono)' : 'var(--font)',
            }}>
              {m.text}
            </div>
          </div>
        ))}
      </div>

      {/* Input */}
      <div style={{ borderTop: '1px solid var(--border)', display: 'flex', padding: '10px 12px', gap: 8, flexShrink: 0 }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          rows={1}
          placeholder="Say something…"
          style={{
            flex: 1, border: '1px solid var(--border)', borderRadius: 6, padding: '7px 10px',
            fontSize: 13, fontFamily: 'var(--font)', color: 'var(--text-primary)',
            background: 'var(--surface)', outline: 'none', resize: 'none', lineHeight: 1.4,
          }}
          onFocus={e => (e.currentTarget.style.borderColor = 'var(--border-dark)')}
          onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
        />
        <button
          onClick={sendMessage}
          style={{ padding: '7px 14px', background: 'var(--text-primary)', color: 'white', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 500, fontFamily: 'var(--font)', cursor: 'pointer', whiteSpace: 'nowrap' }}
          onMouseEnter={e => (e.currentTarget.style.background = '#333')}
          onMouseLeave={e => (e.currentTarget.style.background = 'var(--text-primary)')}
        >Send</button>
      </div>
    </div>
  )
}
