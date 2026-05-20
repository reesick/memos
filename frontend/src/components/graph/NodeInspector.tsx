import { useState } from 'react'
import { api } from '../../api'
import type { GraphNode } from '../../hooks/useGraphData'

interface Props {
  node: GraphNode | null
  onClose: () => void
  onDeleted: (memoryId: string) => void
}

export function NodeInspector({ node, onClose, onDeleted }: Props) {
  const [deleting, setDeleting] = useState(false)

  if (!node) return null

  const isEntity = node.group === 'entity'
  const ts = node.timestamp ? new Date(node.timestamp * 1000) : null

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
      className="fade-in"
      style={{
        position: 'absolute', top: 12, left: 12,
        width: 240,
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 8, padding: 14,
        boxShadow: '0 2px 12px rgba(0,0,0,0.1)',
        zIndex: 20,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
        <div style={{
          fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase',
          color: isEntity ? 'var(--accent)' : 'var(--text-muted)',
          background: isEntity ? 'var(--accent-soft)' : 'var(--surface-2)',
          border: `1px solid ${isEntity ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 3, padding: '1px 6px',
        }}>
          {isEntity ? 'Entity' : 'Fact'}
        </div>
        <button
          onClick={onClose}
          style={{
            marginLeft: 'auto', width: 20, height: 20, border: 'none',
            background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)',
            fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: 3,
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >×</button>
      </div>

      {/* Entity name / value */}
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8, lineHeight: 1.4, wordBreak: 'break-word' }}>
        {isEntity ? node.entity : node.value}
      </div>

      {!isEntity && (
        <>
          <Row label="Entity" value={node.entity} />
          <Row label="Attribute" value={(node.attribute || '').replace(/_/g, ' ')} />
          <Row label="Source" value={node.source_type} />
          <Row label="Session" value={node.session_id?.slice(-8)} mono />
          <Row label="ID" value={node.memory_id?.slice(0, 12) + '…'} mono />
          {ts && <Row label="Stored" value={ts.toLocaleDateString() + ' ' + ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} />}
          {node.expired && (
            <div style={{ marginTop: 6, fontSize: 10, color: 'var(--danger)', fontWeight: 500 }}>⚠ Expired / superseded</div>
          )}

          <button
            onClick={handleDelete}
            disabled={deleting}
            style={{
              marginTop: 12, width: '100%', padding: '5px 0',
              border: '1px solid var(--danger)', color: 'var(--danger)',
              background: 'transparent', borderRadius: 4, cursor: deleting ? 'not-allowed' : 'pointer',
              fontSize: 11, fontWeight: 600, fontFamily: 'var(--font)',
              opacity: deleting ? 0.5 : 1,
            }}
            onMouseEnter={e => !deleting && (e.currentTarget.style.background = '#fef2f2')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            {deleting ? 'Deleting…' : 'Delete fact'}
          </button>
        </>
      )}

      {isEntity && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Double-click to focus graph on this entity.
        </div>
      )}
    </div>
  )
}

function Row({ label, value, mono }: { label: string; value?: string; mono?: boolean }) {
  if (!value) return null
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', fontSize: 11 }}>
      <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', fontFamily: mono ? 'var(--mono)' : 'var(--font)', fontSize: mono ? 10 : 11, textAlign: 'right', marginLeft: 8, wordBreak: 'break-all' }}>
        {value}
      </span>
    </div>
  )
}
