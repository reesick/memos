import { useMemo, useRef, useState } from 'react'
import type { GraphData } from '../../hooks/useGraphData'

interface Props {
  data: GraphData | null
  onSearch: (q: string) => void
  onFocusEntity: (entity: string, hops: number) => void
  onFilterChange: (sourceTypes: string[]) => void
}

export function GraphLeftRail({ data, onSearch, onFocusEntity, onFilterChange }: Props) {
  const [query, setQuery] = useState('')
  const [showDropdown, setShowDropdown] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [filterOpen, setFilterOpen] = useState(false)
  const [activeSourceTypes, setActiveSourceTypes] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const suggestions = useMemo(() => {
    if (!query || !data) return []
    const lower = query.toLowerCase()
    const entityMatches = data.entityNames
      .filter(n => n.toLowerCase().includes(lower))
      .slice(0, 4)
      .map(n => ({ type: 'entity' as const, label: n, sub: '' }))
    const seen = new Set(entityMatches.map(e => e.label.toLowerCase()))
    const factMatches: { type: 'fact'; label: string; sub: string }[] = []
    for (const n of data.nodes) {
      if (n.group !== 'fact') continue
      const val = String(n.value ?? '')
      const attr = String(n.attribute ?? '').replace(/_/g, ' ')
      if (val.toLowerCase().includes(lower) && !seen.has(val.toLowerCase())) {
        seen.add(val.toLowerCase())
        factMatches.push({ type: 'fact', label: val.length > 32 ? val.slice(0, 32) + '…' : val, sub: attr })
        if (factMatches.length >= 3) break
      }
    }
    return [...entityMatches, ...factMatches]
  }, [query, data])

  const matchCount = useMemo(() => {
    if (!query || !data) return 0
    const lower = query.toLowerCase()
    return data.nodes.filter(n =>
      String(n.label).toLowerCase().includes(lower) ||
      String(n.value ?? '').toLowerCase().includes(lower) ||
      String(n.attribute ?? '').toLowerCase().includes(lower)
    ).length
  }, [query, data])

  const sourceTypeCounts = useMemo(() => {
    if (!data) return {} as Record<string, number>
    return data.nodes
      .filter(n => n.group === 'fact')
      .reduce((acc, n) => {
        const t = n.source_type || 'text'
        acc[t] = (acc[t] || 0) + 1
        return acc
      }, {} as Record<string, number>)
  }, [data])

  function handleQueryChange(val: string) {
    setQuery(val)
    setActiveIdx(-1)
    setShowDropdown(val.length > 0)
    onSearch(val)
    if (!val) onFilterChange([])
  }

  function selectSuggestion(s: { type: 'entity' | 'fact'; label: string; sub: string }) {
    setQuery('')
    setShowDropdown(false)
    onSearch('')
    if (s.type === 'entity') {
      onFocusEntity(s.label, 2)
    } else {
      // For fact matches, highlight the query across the full graph
      onSearch(s.label)
    }
    inputRef.current?.blur()
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown' && showDropdown) {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp' && showDropdown) {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0 && suggestions[activeIdx]) {
        selectSuggestion(suggestions[activeIdx])
      } else if (suggestions.length === 1) {
        selectSuggestion(suggestions[0])
      }
      // else: free-form query already live-highlighted on canvas — nothing more to do
    } else if (e.key === 'Escape') {
      setShowDropdown(false)
      setQuery('')
      onSearch('')
    }
  }

  function toggleSourceType(t: string) {
    const next = activeSourceTypes.includes(t)
      ? activeSourceTypes.filter(x => x !== t)
      : [...activeSourceTypes, t]
    setActiveSourceTypes(next)
    onFilterChange(next)
  }

  const topEntities = data?.topEntities ?? []

  return (
    <div style={{
      width: 220, flexShrink: 0,
      background: 'var(--surface)', borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%',
    }}>
      {/* ── Search ── */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 7 }}>
          Search
        </div>
        <div style={{ position: 'relative' }}>
          <input
            id="graph-search"
            ref={inputRef}
            value={query}
            onChange={e => handleQueryChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => query && setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
            placeholder="Entity name or fact…"
            style={{
              width: '100%', boxSizing: 'border-box',
              border: '1px solid var(--border)', borderRadius: 5,
              padding: '6px 8px 6px 28px', fontSize: 11, fontFamily: 'var(--font)',
              background: 'var(--surface)', color: 'var(--text-primary)', outline: 'none',
            }}
            onFocusCapture={e => (e.currentTarget.style.borderColor = 'var(--border-dark)')}
            onBlurCapture={e => (e.currentTarget.style.borderColor = 'var(--border)')}
          />
          <svg style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="5" cy="5" r="3.5" stroke="#aaa" strokeWidth="1.2" />
            <line x1="7.7" y1="7.7" x2="10" y2="10" stroke="#aaa" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          {query && (
            <button
              onMouseDown={e => { e.preventDefault(); setQuery(''); setShowDropdown(false); onSearch('') }}
              style={{
                position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 12, color: 'var(--text-muted)', lineHeight: 1, padding: '0 2px',
              }}
              tabIndex={-1}
            >×</button>
          )}

          {/* Autocomplete dropdown */}
          {showDropdown && suggestions.length > 0 && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 5, marginTop: 2, boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              overflow: 'hidden',
            }}>
              {suggestions.map((s, i) => (
                <div
                  key={`${s.type}-${s.label}`}
                  onMouseDown={() => selectSuggestion(s)}
                  style={{
                    padding: '6px 10px', fontSize: 12, cursor: 'pointer',
                    background: i === activeIdx ? 'var(--accent-soft)' : 'transparent',
                    borderBottom: i < suggestions.length - 1 ? '1px solid var(--border)' : 'none',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <span style={{
                    fontSize: 8, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                    color: s.type === 'entity' ? '#16a34a' : 'var(--text-muted)',
                    background: s.type === 'entity' ? '#dcfce7' : 'var(--surface-2)',
                    border: `1px solid ${s.type === 'entity' ? '#bbf7d0' : 'var(--border)'}`,
                    borderRadius: 3, padding: '1px 4px', flexShrink: 0,
                  }}>
                    {s.type}
                  </span>
                  <div style={{ overflow: 'hidden' }}>
                    <div style={{ color: i === activeIdx ? 'var(--accent)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {s.label}
                    </div>
                    {s.sub && (
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>{s.sub}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {query && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 5, fontFamily: 'var(--mono)' }}>
            {matchCount} match{matchCount !== 1 ? 'es' : ''}
          </div>
        )}
      </div>

      {/* ── Quick Explore ── */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }} id="tour-quick-explore">
        <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 7 }}>
          Start here
        </div>
        {topEntities.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>No entities yet.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {topEntities.map(({ entity, factCount }) => (
              <button
                key={entity}
                onClick={() => onFocusEntity(entity, 2)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 8px', background: 'transparent',
                  border: '1px solid transparent', borderRadius: 4, cursor: 'pointer',
                  fontFamily: 'var(--font)', textAlign: 'left',
                  transition: 'all 0.1s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'var(--accent-soft)'
                  e.currentTarget.style.borderColor = 'var(--accent)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.borderColor = 'transparent'
                }}
              >
                <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                  {entity}
                </span>
                <span style={{
                  fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--mono)',
                  background: 'var(--accent-soft)', borderRadius: 3, padding: '1px 5px',
                  marginLeft: 6, flexShrink: 0,
                }}>
                  {factCount}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Filter ── */}
      <div style={{ padding: '0', borderBottom: '1px solid var(--border)' }}>
        <button
          onClick={() => setFilterOpen(o => !o)}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 12px', background: 'transparent', border: 'none', cursor: 'pointer',
            fontFamily: 'var(--font)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              Filter
            </span>
            {activeSourceTypes.length > 0 && (
              <span style={{
                fontSize: 9, color: 'var(--accent)', background: 'var(--accent-soft)',
                borderRadius: 3, padding: '1px 5px', fontFamily: 'var(--mono)', fontWeight: 600,
              }}>
                {activeSourceTypes.length}
              </span>
            )}
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', transition: 'transform 0.15s', display: 'inline-block', transform: filterOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}>▾</span>
        </button>

        {filterOpen && (
          <div style={{ padding: '0 12px 10px' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 7 }}>Source type</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {Object.entries(sourceTypeCounts).map(([t, c]) => {
                const active = activeSourceTypes.includes(t)
                return (
                  <button
                    key={t}
                    onClick={() => toggleSourceType(t)}
                    style={{
                      padding: '3px 8px', fontSize: 10, fontWeight: 500,
                      background: active ? 'var(--accent-soft)' : 'var(--surface-2)',
                      border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                      color: active ? 'var(--accent)' : 'var(--text-muted)',
                      borderRadius: 3, cursor: 'pointer', fontFamily: 'var(--mono)',
                    }}
                  >
                    {t} <span style={{ opacity: 0.7 }}>{c}</span>
                  </button>
                )
              })}
              {Object.keys(sourceTypeCounts).length === 0 && (
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>No data yet.</span>
              )}
            </div>
            {activeSourceTypes.length > 0 && (
              <button
                onClick={() => { setActiveSourceTypes([]); onFilterChange([]) }}
                style={{
                  marginTop: 8, fontSize: 10, color: 'var(--text-muted)', background: 'transparent',
                  border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline', fontFamily: 'var(--font)',
                }}
              >
                Clear filter
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
