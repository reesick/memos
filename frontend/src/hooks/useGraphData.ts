import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Memory } from '../types'

export interface GraphNode {
  id: string
  label: string
  title: string
  group: 'entity' | 'fact'
  size: number
  color: object
  font: object
  borderWidth?: number
  // raw data
  entity?: string
  attribute?: string
  value?: string
  source_type?: string
  session_id?: string
  timestamp?: number
  memory_id?: string
  expired?: boolean
}

export interface GraphEdge {
  id: string
  from: string
  to: string
  label: string
  dashes?: boolean
  color?: object
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  memories: Memory[]
  entityNames: string[]
  attributes: string[]
  sessions: string[]
  oldestTs: number
  newestTs: number
  topEntities: { entity: string; factCount: number }[]
}

function memoriesToGraph(memories: Memory[]): GraphData {
  const nodeMap = new Map<string, GraphNode>()
  const edgeMap = new Map<string, GraphEdge>()
  const entityDegree = new Map<string, number>()

  // Log first 3 raw memories so we can see exactly what the API returns
  if (memories.length > 0) {
    console.group('[useGraphData] raw API sample (first 3)')
    memories.slice(0, 3).forEach((m, i) => {
      console.log(`[${i}] value type=${typeof m.value} val=${JSON.stringify(m.value)}`)
      console.log(`    attribute type=${typeof m.attribute} val=${JSON.stringify(m.attribute)}`)
      console.log(`    timestamp type=${typeof m.timestamp} val=${JSON.stringify(m.timestamp)}`)
      console.log(`    source_type type=${typeof m.source_type} val=${JSON.stringify(m.source_type)}`)
    })
    console.groupEnd()
  }

  for (const m of memories) {
    const factId = String(m.memory_id ?? '')
    if (!factId) continue

    // Coerce every API field to its expected type at ingestion — never trust raw API types
    const entity = String(m.entity || '(unknown)')
    const val = String(m.value ?? '')
    const attr = String(m.attribute ?? '')
    const sourceType = String(m.source_type ?? 'text')
    const sessionId = String(m.session_id ?? '')
    const tsRaw = Number(m.timestamp)
    const timestamp = isFinite(tsRaw) && tsRaw > 0 ? tsRaw : undefined
    const expired = Boolean(m.expired_at)

    const entityId = `entity_${entity}`

    if (!nodeMap.has(entityId)) {
      nodeMap.set(entityId, {
        id: entityId,
        label: entity,
        title: `Entity: ${entity}`,
        group: 'entity',
        size: 20,
        entity,
        borderWidth: 2.5,
        color: { background: '#dcfce7', border: '#16a34a', highlight: { background: '#bbf7d0', border: '#15803d' } },
        font: { color: '#111111', size: 12, face: 'Geist, sans-serif' },
      })
    }
    entityDegree.set(entityId, (entityDegree.get(entityId) ?? 0) + 1)

    if (!nodeMap.has(factId)) {
      const attrLabel = attr.replace(/_/g, ' ')
      nodeMap.set(factId, {
        id: factId,
        label: val.slice(0, 20) + (val.length > 20 ? '…' : ''),
        title: `${attrLabel}: ${val}`,
        group: 'fact',
        size: 8,
        entity,
        attribute: attr,
        value: val,
        source_type: sourceType,
        session_id: sessionId,
        timestamp,
        memory_id: factId,
        expired,
        color: expired
          ? { background: '#f5f5f5', border: '#d0d0d0', highlight: { background: '#f5f5f5', border: '#999' } }
          : { background: '#f5f5f5', border: '#d0d0d0', highlight: { background: '#dcfce7', border: '#16a34a' } },
        font: { color: '#555555', size: 0, face: 'Geist, sans-serif' },
      })
    }

    const edgeId = `edge_${entityId}_${factId}`
    if (!edgeMap.has(edgeId)) {
      edgeMap.set(edgeId, {
        id: edgeId,
        from: entityId,
        to: factId,
        label: attr.replace(/_/g, ' ').slice(0, 14),
        dashes: expired,
        color: expired
          ? { color: '#cccccc', highlight: '#cccccc' }
          : { color: '#d0d0d0', highlight: '#16a34a' },
      })
    }
  }

  // Scale entity node sizes (20–36px) by degree
  for (const [id, degree] of entityDegree) {
    const node = nodeMap.get(id)
    if (node) node.size = Math.max(20, Math.min(36, 14 + degree * 2.5))
  }

  const memories_sorted = [...memories].sort((a, b) => (a.timestamp ?? 0) - (b.timestamp ?? 0))
  const oldestTs = memories_sorted[0]?.timestamp ?? Date.now() / 1000
  const newestTs = memories_sorted[memories_sorted.length - 1]?.timestamp ?? Date.now() / 1000

  const entityNames = [...new Set(memories.map(m => m.entity).filter(Boolean))] as string[]
  const attributes = [...new Set(memories.map(m => m.attribute).filter(Boolean))] as string[]
  const sessions = [...new Set(memories.map(m => m.session_id).filter(Boolean))] as string[]

  const topEntities = [...entityDegree.entries()]
    .map(([id, factCount]) => ({ entity: id.replace(/^entity_/, ''), factCount }))
    .sort((a, b) => b.factCount - a.factCount)
    .slice(0, 5)

  return {
    nodes: [...nodeMap.values()],
    edges: [...edgeMap.values()],
    memories,
    entityNames,
    attributes,
    sessions,
    oldestTs,
    newestTs,
    topEntities,
  }
}

export function useGraphData(refreshInterval = 10_000) {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function load() {
    try {
      const res = await api.listMemories(500)
      setData(memoriesToGraph(res.memories as (Memory & { expired_at?: string | null })[]))
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    timerRef.current = setInterval(load, refreshInterval)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [refreshInterval])

  return { data, loading, error, refresh: load }
}
