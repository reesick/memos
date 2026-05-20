import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Memory } from '../types'
import { api } from '../api'

interface Props {
  refreshKey: number
  onMemoriesLoaded: (mems: Memory[]) => void
}

export function MemoriesPanel({ refreshKey, onMemoriesLoaded }: Props) {
  const [memories, setMemories] = useState<Memory[]>([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [isSearch, setIsSearch] = useState(false)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => { loadMemories() }, [refreshKey])

  async function loadMemories() {
    setLoading(true)
    try {
      const d = await api.listMemories(50)
      setTotal(d.total)
      setMemories(d.memories)
      onMemoriesLoaded(d.memories)
      setIsSearch(false)
    } catch {
      setMemories([])
    } finally {
      setLoading(false)
    }
  }

  async function searchMemories() {
    const q = query.trim()
    if (!q) { loadMemories(); return }
    setLoading(true)
    try {
      const d = await api.searchMemories(q, 20)
      setMemories(d.results)
      setIsSearch(true)
    } catch {
      setMemories([])
    } finally {
      setLoading(false)
    }
  }

  function renderHighlighted(text: string, q: string) {
    if (!q || !isSearch) return <>{text}</>
    const esc = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const parts = text.split(new RegExp(`(${esc})`, 'gi'))
    return (
      <>
        {parts.map((p, i) =>
          p.toLowerCase() === q.toLowerCase()
            ? <em key={i} style={{ color: 'var(--accent)', fontStyle: 'normal', fontWeight: 600 }}>{p}</em>
            : p
        )}
      </>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--surface)', borderRight: '1px solid var(--border)', height: '100%' }}>
      {/* Header */}
      <div style={{ height: 40, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 16px', gap: 8, flexShrink: 0 }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Memories</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>{total}</span>
      </div>

      {/* Search */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 6, flexShrink: 0 }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && searchMemories()}
          placeholder="Search memories…"
          style={{ flex: 1, border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px', fontSize: 12, fontFamily: 'var(--font)', background: 'var(--surface)', color: 'var(--text-primary)', outline: 'none' }}
          onFocus={e => (e.currentTarget.style.borderColor = 'var(--border-dark)')}
          onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
        />
        <button
          onClick={searchMemories}
          style={{ padding: '6px 12px', background: 'var(--text-primary)', color: 'white', border: 'none', borderRadius: 6, fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', cursor: 'pointer', fontFamily: 'var(--font)' }}
        >Search</button>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {loading && <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 11, padding: 20, fontFamily: 'var(--mono)' }}>loading…</div>}
        {!loading && memories.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 12, padding: '40px 20px' }}>
            {isSearch ? 'No memories found.' : 'No memories yet.\nStart a conversation to store facts.'}
          </div>
        )}
        {!loading && memories.map(m => {
          const ts = m.timestamp ? new Date(m.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
          const attr = String(m.attribute ?? '').replace(/_/g, ' ')
          const isHovered = hoveredId === m.memory_id
          const isSelected = selected === m.memory_id

          return (
            <div
              key={m.memory_id}
              className="fade-in"
              onClick={() => setSelected(isSelected ? null : m.memory_id)}
              onMouseEnter={() => setHoveredId(m.memory_id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                padding: '10px 14px', borderBottom: '1px solid var(--border)', cursor: 'pointer',
                background: isSelected ? '#f0fdf4' : isHovered ? 'var(--surface-2)' : 'transparent',
                borderLeft: isSelected ? '2px solid var(--accent)' : '2px solid transparent',
                transition: 'background 0.1s ease',
                position: 'relative',
              }}
            >
              <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500, marginBottom: 3, paddingRight: isHovered && m.entity ? 28 : 0 }}>
                {m.entity && <strong>{m.entity}</strong>}
                {m.entity && ' · '}
                {renderHighlighted(String(m.value ?? ''), query)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--mono)', display: 'flex', gap: 8 }}>
                <span style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>{attr}</span>
                <span style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>{m.source_type || 'text'}</span>
                <span style={{ marginLeft: 'auto' }}>{ts}</span>
              </div>

              {/* View in graph hover icon */}
              {isHovered && m.entity && (
                <button
                  onClick={e => { e.stopPropagation(); navigate(`/graph?focus=${encodeURIComponent(m.entity)}`) }}
                  title={`View ${m.entity} in graph`}
                  className="fade-in"
                  style={{
                    position: 'absolute', top: 10, right: 10,
                    width: 22, height: 22, border: '1px solid var(--border)',
                    borderRadius: 4, background: 'var(--surface)', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'var(--accent)',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-soft)'; e.currentTarget.style.borderColor = 'var(--accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.borderColor = 'var(--border)' }}
                >
                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                    <circle cx="2" cy="2" r="1.5" fill="currentColor" />
                    <circle cx="10" cy="2" r="1.5" fill="currentColor" />
                    <circle cx="6" cy="10" r="1.5" fill="currentColor" />
                    <line x1="2" y1="2" x2="10" y2="2" stroke="currentColor" strokeWidth="1" />
                    <line x1="2" y1="2" x2="6" y2="10" stroke="currentColor" strokeWidth="1" />
                    <line x1="10" y1="2" x2="6" y2="10" stroke="currentColor" strokeWidth="1" />
                  </svg>
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
