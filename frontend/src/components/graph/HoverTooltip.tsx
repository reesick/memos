import type { GraphNode, GraphData } from '../../hooks/useGraphData'

interface Props {
  node: GraphNode | null
  x: number
  y: number
  data: GraphData | null
}

function timeAgo(ts: number | undefined): string {
  const n = Number(ts)
  if (!isFinite(n) || n <= 0) {
    if (ts !== undefined) console.warn('[timeAgo HoverTooltip] bad input:', ts, typeof ts)
    return ''
  }
  const diff = Date.now() / 1000 - n
  if (diff < 0) return 'just now'
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

export function HoverTooltip({ node, x, y, data }: Props) {
  if (!node) return null

  const isEntity = node.group === 'entity'

  let entityFactCount = 0
  let entitySources = ''
  if (isEntity && data) {
    const facts = data.nodes.filter(n => n.group === 'fact' && n.entity === node.entity)
    entityFactCount = facts.length
    const sourceCounts = facts.reduce((acc, f) => {
      const t = f.source_type || 'text'
      acc[t] = (acc[t] || 0) + 1
      return acc
    }, {} as Record<string, number>)
    entitySources = Object.entries(sourceCounts)
      .map(([t, c]) => `${t} ${c}`)
      .join(' · ')
  }

  const left = x + 14
  const top = y + 14

  return (
    <div
      style={{
        position: 'fixed',
        left,
        top,
        zIndex: 500,
        pointerEvents: 'none',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '8px 10px',
        boxShadow: '0 2px 10px rgba(0,0,0,0.12)',
        minWidth: 140,
        maxWidth: 200,
        animation: 'fadeIn 0.1s ease',
      }}
    >
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 3 }}>
        {isEntity ? 'ENTITY' : `FACT · ${String(node.attribute ?? '').replace(/_/g, ' ')}`}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3, marginBottom: 5, wordBreak: 'break-word' }}>
        {isEntity ? node.entity : String(node.value ?? '')}
      </div>
      <div style={{ width: 20, height: 1, background: 'var(--border)', marginBottom: 5 }} />
      {isEntity ? (
        <>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {entityFactCount} fact{entityFactCount !== 1 ? 's' : ''}
            {entitySources ? ` · ${entitySources}` : ''}
          </div>
          <div style={{ fontSize: 10, color: 'var(--accent)', marginTop: 3 }}>Click to inspect</div>
        </>
      ) : (
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          {node.entity && <span>{node.entity} · </span>}
          {node.source_type && <span>{node.source_type} · </span>}
          {node.timestamp && <span>{timeAgo(node.timestamp)}</span>}
        </div>
      )}
    </div>
  )
}
