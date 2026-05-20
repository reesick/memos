import { useState } from 'react'
import { api } from '../../api'
import type { GraphNode, GraphData } from '../../hooks/useGraphData'

interface Props {
  node: GraphNode | null
  data: GraphData | null
  onClose: () => void
  onDeleted: (memoryId: string) => void
  onFocusEntity: (entity: string) => void
  onClearFocus: () => void
  focusedEntity: string | null
}

function timeAgo(ts: number | undefined): string {
  const n = Number(ts)
  if (!isFinite(n) || n <= 0) {
    if (ts !== undefined) console.warn('[timeAgo RightInspector] bad input:', ts, typeof ts)
    return ''
  }
  const diff = Date.now() / 1000 - n
  if (diff < 0) return 'just now'
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

export function RightInspector({ node, data, onClose, onDeleted, onFocusEntity, onClearFocus, focusedEntity }: Props) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    if (!node?.memory_id) return
    if (!confirm(`Delete fact "${node.value}"?`)) return
    setDeleting(true)
    try {
      await api.deleteMemory(node.memory_id)
      onDeleted(node.memory_id)
      onClose()
    } catch {
      alert('Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div
      style={{
        width: 260,
        flexShrink: 0,
        background: 'var(--surface)',
        borderLeft: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        height: '100%',
      }}
      id="tour-right-rail"
    >
      {/* Header */}
      <div style={{
        height: 40, borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', padding: '0 14px', flexShrink: 0,
      }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
          Inspector
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {!node ? (
          <CoachCard />
        ) : node.group === 'entity' ? (
          <EntityDetail node={node} data={data} onFocusEntity={onFocusEntity} onClearFocus={onClearFocus} focusedEntity={focusedEntity} />
        ) : (
          <FactDetail node={node} onFocusEntity={onFocusEntity} onDelete={handleDelete} deleting={deleting} />
        )}
      </div>
    </div>
  )
}

function CoachCard() {
  return (
    <div style={{ padding: '20px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#dcfce7', border: '2px solid #16a34a' }} />
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#f5f5f5', border: '1px solid #d0d0d0' }} />
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8, lineHeight: 1.4 }}>
        Pick a dot to inspect
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.65 }}>
        <strong style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Green dots</strong> are entities — people or things MemoryOS knows about.
        <br /><br />
        <strong style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Small gray dots</strong> are individual facts linked to those entities.
        <br /><br />
        Hover any dot for a quick preview. Click to see full details here.
      </div>
      <div style={{
        marginTop: 16, padding: '10px 12px', background: 'var(--surface-2)',
        borderRadius: 6, border: '1px solid var(--border)', fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5,
      }}>
        Tip: use <strong>Start here</strong> on the left to jump to a specific entity, or type in the search box to find a fact.
      </div>
    </div>
  )
}

function EntityDetail({ node, data, onFocusEntity, onClearFocus, focusedEntity }: {
  node: GraphNode
  data: GraphData | null
  onFocusEntity: (entity: string) => void
  onClearFocus: () => void
  focusedEntity: string | null
}) {
  const [showAll, setShowAll] = useState(false)

  const facts = data ? data.nodes.filter(n => n.group === 'fact' && n.entity === node.entity) : []
  const activeFacts = facts.filter(f => !f.expired)
  const expiredFacts = facts.filter(f => f.expired)
  const PAGE = 8
  const displayed = showAll ? activeFacts : activeFacts.slice(0, PAGE)
  const remaining = activeFacts.length - PAGE

  const sourceCounts = facts.reduce((acc, f) => {
    const t = String(f.source_type || 'text')
    acc[t] = (acc[t] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const isFocused = focusedEntity === node.entity
  console.log(`[RightInspector] EntityDetail | node.entity="${node.entity}" | focusedEntity="${focusedEntity}" | isFocused=${isFocused}`)

  return (
    <div style={{ padding: '14px 16px' }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 6 }}>Entity</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{node.entity}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 14 }}>
        {facts.length} fact{facts.length !== 1 ? 's' : ''}
        {expiredFacts.length > 0 && (
          <span style={{ color: 'var(--danger)', marginLeft: 6 }}>· {expiredFacts.length} expired</span>
        )}
      </div>

      {/* Source breakdown */}
      {Object.keys(sourceCounts).length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
          {Object.entries(sourceCounts).map(([t, c]) => (
            <span key={t} style={{
              fontSize: 10, color: 'var(--text-muted)', background: 'var(--surface-2)',
              border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontFamily: 'var(--mono)',
            }}>
              {t} {c}
            </span>
          ))}
        </div>
      )}

      {/* Fact list */}
      {activeFacts.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>Facts</div>
          {displayed.map(f => {
            const val = String(f.value ?? '')
            const attr = String(f.attribute ?? '').replace(/_/g, ' ')
            const display = val.length > 60 ? val.slice(0, 60) + '…' : val
            return (
              <div key={f.id} style={{ padding: '5px 0', borderBottom: '1px solid var(--border)', fontSize: 11, lineHeight: 1.4 }}>
                <div style={{ color: 'var(--text-muted)', fontSize: 10, marginBottom: 1 }}>{attr}</div>
                <div style={{ color: 'var(--text-primary)' }}>{display}</div>
              </div>
            )
          })}
          {!showAll && remaining > 0 && (
            <button
              onClick={() => setShowAll(true)}
              style={{
                marginTop: 6, fontSize: 11, color: 'var(--accent)', background: 'transparent',
                border: 'none', cursor: 'pointer', padding: '2px 0', fontFamily: 'var(--font)',
                textDecoration: 'underline',
              }}
            >
              +{remaining} more
            </button>
          )}
          {showAll && activeFacts.length > PAGE && (
            <button
              onClick={() => setShowAll(false)}
              style={{
                marginTop: 6, fontSize: 11, color: 'var(--text-muted)', background: 'transparent',
                border: 'none', cursor: 'pointer', padding: '2px 0', fontFamily: 'var(--font)',
                textDecoration: 'underline',
              }}
            >
              Show less
            </button>
          )}
        </div>
      )}

      {/* Focus button — toggles: focus when unfocused, clear when already focused */}
      <button
        onClick={() => {
          if (isFocused) onClearFocus()
          else if (node.entity) onFocusEntity(node.entity)
        }}
        style={{
          width: '100%', padding: '7px 0', fontSize: 11, fontWeight: 600,
          background: isFocused ? 'var(--surface-2)' : 'var(--accent)',
          color: isFocused ? 'var(--text-secondary)' : 'white',
          border: `1px solid ${isFocused ? 'var(--border)' : 'var(--accent)'}`,
          borderRadius: 5, cursor: 'pointer', fontFamily: 'var(--font)',
          letterSpacing: '0.02em',
        }}
      >
        {isFocused ? 'Clear focus ×' : 'Focus this entity ▸'}
      </button>
    </div>
  )
}

function FactDetail({ node, onFocusEntity, onDelete, deleting }: {
  node: GraphNode
  onFocusEntity: (entity: string) => void
  onDelete: () => void
  deleting: boolean
}) {
  const tsNum = Number(node.timestamp)
  const ts = isFinite(tsNum) && tsNum > 0 ? new Date(tsNum * 1000) : null
  return (
    <div style={{ padding: '14px 16px' }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>
        Fact · {String(node.attribute ?? '').replace(/_/g, ' ')}
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12, lineHeight: 1.4, wordBreak: 'break-word' }}>
        {String(node.value ?? '')}
      </div>

      {node.expired && (
        <div style={{ marginBottom: 10, fontSize: 11, color: 'var(--danger)', fontWeight: 500 }}>⚠ Expired / superseded</div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 14 }}>
        {node.entity && (
          <Row label="Entity">
            <button
              onClick={() => node.entity && onFocusEntity(node.entity)}
              style={{
                fontSize: 11, color: 'var(--accent)', background: 'transparent', border: 'none',
                cursor: 'pointer', padding: 0, fontFamily: 'var(--font)', fontWeight: 500,
                textDecoration: 'underline',
              }}
            >{node.entity}</button>
          </Row>
        )}
        <Row label="Source">{node.source_type || 'text'}</Row>
        {node.session_id && <Row label="Session"><span style={{ fontFamily: 'var(--mono)', fontSize: 10 }}>{node.session_id.slice(-10)}</span></Row>}
        {ts && (
          <Row label="Stored">
            <span title={ts.toLocaleString()}>{timeAgo(tsNum)}</span>
          </Row>
        )}
      </div>

      <button
        onClick={onDelete}
        disabled={deleting}
        style={{
          width: '100%', padding: '6px 0',
          border: '1px solid var(--danger)', color: 'var(--danger)',
          background: 'transparent', borderRadius: 5, cursor: deleting ? 'not-allowed' : 'pointer',
          fontSize: 11, fontWeight: 600, fontFamily: 'var(--font)',
          opacity: deleting ? 0.5 : 1,
        }}
        onMouseEnter={e => !deleting && (e.currentTarget.style.background = '#fef2f2')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        {deleting ? 'Deleting…' : 'Delete fact'}
      </button>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 0', fontSize: 11 }}>
      <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', textAlign: 'right', marginLeft: 8 }}>{children}</span>
    </div>
  )
}
