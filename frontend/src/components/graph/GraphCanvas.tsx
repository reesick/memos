import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { Network, DataSet } from 'vis-network/standalone'
import type { GraphNode, GraphEdge } from '../../hooks/useGraphData'

export interface GraphCanvasRef {
  fit: () => void
  zoomIn: () => void
  zoomOut: () => void
  focusNode: (id: string) => void
  highlightNodes: (ids: Set<string>) => void
  clearHighlight: () => void
  pulseNode: (id: string) => void
  getNetwork: () => Network | null
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  onSelectNode: (node: GraphNode | null) => void
  onHoverNode: (node: GraphNode | null) => void
}

const PHYSICS_BASE = {
  enabled: true,
  stabilization: { iterations: 100, updateInterval: 20 },
  barnesHut: {
    gravitationalConstant: -3500,
    springLength: 140,
    springConstant: 0.04,
    damping: 0.4,
  },
}

export const GraphCanvas = forwardRef<GraphCanvasRef, Props>(function GraphCanvas(
  { nodes, edges, onSelectNode, onHoverNode },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const nodesDs = useRef(new DataSet<object>([]))
  const edgesDs = useRef(new DataSet<object>([]))
  const allNodeColors = useRef(new Map<string, object>())

  useEffect(() => {
    const existingIds = new Set(nodesDs.current.getIds() as string[])
    const incomingIds = new Set(nodes.map(n => n.id))

    for (const id of existingIds) {
      if (!incomingIds.has(id)) {
        nodesDs.current.update({ id, size: 0, font: { size: 0 } })
        setTimeout(() => nodesDs.current.remove(id), 200)
        edgesDs.current.remove(
          (edgesDs.current.getIds() as string[]).filter(eid => {
            const e = edgesDs.current.get(eid) as GraphEdge | null
            return e && (e.from === id || e.to === id)
          })
        )
      }
    }

    for (const n of nodes) {
      allNodeColors.current.set(n.id, (n as { color: object }).color)
      if (!existingIds.has(n.id)) {
        nodesDs.current.add({ ...n, size: 0, opacity: 1 })
        setTimeout(() => nodesDs.current.update({ id: n.id, size: n.size }), 50)
      } else {
        nodesDs.current.update({ ...n, opacity: 1 })
      }
    }

    const existingEdgeIds = new Set(edgesDs.current.getIds() as string[])
    const incomingEdgeIds = new Set(edges.map(e => e.id))
    for (const id of existingEdgeIds) {
      if (!incomingEdgeIds.has(id)) edgesDs.current.remove(id)
    }
    for (const e of edges) {
      const edgeData = { ...e, font: { size: 0 } }
      if (!existingEdgeIds.has(e.id)) {
        edgesDs.current.add(edgeData)
      } else {
        edgesDs.current.update(edgeData)
      }
    }
  }, [nodes, edges])

  useEffect(() => {
    if (!containerRef.current) return
    const options = {
      nodes: { shape: 'dot', borderWidth: 1.5 },
      edges: {
        width: 1,
        smooth: { enabled: true, type: 'curvedCW' as const, roundness: 0.15 },
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        font: { size: 0 },
        scaling: { min: 1, max: 2 },
      },
      physics: PHYSICS_BASE,
      interaction: {
        hover: true,
        tooltipDelay: 999999,
        multiselect: false,
        navigationButtons: false,
        keyboard: false,
      },
    }
    const net = new Network(
      containerRef.current,
      { nodes: nodesDs.current, edges: edgesDs.current },
      options
    )
    networkRef.current = net

    net.on('click', params => {
      if (params.nodes.length === 0) {
        onSelectNode(null)
        clearHighlightInternal()
        return
      }
      const id = params.nodes[0] as string
      const node = nodesDs.current.get(id) as GraphNode | null
      if (node) {
        onSelectNode(node)
        highlightNeighborhood(id)
      }
    })

    net.on('hoverNode', (params: { node: string }) => {
      const node = nodesDs.current.get(params.node) as GraphNode | null
      onHoverNode(node)
    })

    net.on('blurNode', () => {
      onHoverNode(null)
    })

    net.on('stabilized', () => {
      net.setOptions({ physics: { stabilization: { iterations: 30 } } })
    })

    return () => net.destroy()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function highlightNeighborhood(centerId: string) {
    const connectedEdges = networkRef.current?.getConnectedEdges(centerId) as string[] ?? []
    const connectedNodes = new Set<string>([centerId])
    for (const eid of connectedEdges) {
      const e = edgesDs.current.get(eid) as GraphEdge | null
      if (e) { connectedNodes.add(e.from as string); connectedNodes.add(e.to as string) }
    }
    const allIds = nodesDs.current.getIds() as string[]
    for (const id of allIds) {
      const orig = allNodeColors.current.get(id) as { background: string; border: string } | undefined
      if (!orig) continue
      const node = nodesDs.current.get(id) as GraphNode | null
      const isFact = node?.group === 'fact'
      if (connectedNodes.has(id)) {
        nodesDs.current.update({
          id, color: orig, opacity: 1,
          ...(isFact ? { font: { color: '#555555', size: 10, face: 'Geist, sans-serif' } } : {}),
        })
      } else {
        nodesDs.current.update({ id, color: { background: orig.background, border: orig.border }, opacity: 0.15 })
      }
    }
    for (const eid of edgesDs.current.getIds() as string[]) {
      const isConnected = connectedEdges.includes(eid)
      edgesDs.current.update({
        id: eid,
        color: isConnected ? { color: '#16a34a' } : { color: '#f0f0f0' },
        font: isConnected ? { size: 9, color: '#999', face: 'Geist Mono, monospace' } : { size: 0 },
      })
    }
  }

  function clearHighlightInternal() {
    for (const id of nodesDs.current.getIds() as string[]) {
      const orig = allNodeColors.current.get(id)
      const node = nodesDs.current.get(id) as GraphNode | null
      if (orig) {
        nodesDs.current.update({
          id, color: orig, opacity: 1,
          ...(node?.group === 'fact' ? { font: { size: 0 } } : {}),
        })
      }
    }
    for (const eid of edgesDs.current.getIds() as string[]) {
      const e = edgesDs.current.get(eid) as GraphEdge | null
      if (e) edgesDs.current.update({ id: eid, color: e.dashes ? { color: '#cccccc' } : { color: '#d0d0d0' }, font: { size: 0 } })
    }
  }

  useImperativeHandle(ref, () => ({
    fit() {
      networkRef.current?.fit({ animation: { duration: 450, easingFunction: 'easeInOutQuad' } })
    },
    zoomIn() {
      const s = networkRef.current?.getScale() ?? 1
      networkRef.current?.moveTo({ scale: s * 1.3, animation: { duration: 200, easingFunction: 'easeInOutQuad' } })
    },
    zoomOut() {
      const s = networkRef.current?.getScale() ?? 1
      networkRef.current?.moveTo({ scale: s * 0.75, animation: { duration: 200, easingFunction: 'easeInOutQuad' } })
    },
    focusNode(id: string) {
      const pos = networkRef.current?.getPosition(id)
      if (pos) {
        networkRef.current?.moveTo({
          position: pos,
          scale: 1.8,
          animation: { duration: 450, easingFunction: 'easeInOutQuad' },
        })
        const node = nodesDs.current.get(id) as GraphNode | null
        if (node) { onSelectNode(node); highlightNeighborhood(id) }
      }
    },
    highlightNodes(ids: Set<string>) {
      for (const id of nodesDs.current.getIds() as string[]) {
        const orig = allNodeColors.current.get(id) as { background: string; border: string } | undefined
        if (!orig) continue
        nodesDs.current.update({ id, color: orig, opacity: ids.has(id) ? 1 : 0.12 })
      }
      for (const eid of edgesDs.current.getIds() as string[]) {
        const e = edgesDs.current.get(eid) as GraphEdge | null
        if (!e) continue
        const active = ids.has(e.from as string) || ids.has(e.to as string)
        edgesDs.current.update({ id: eid, color: active ? { color: '#16a34a' } : { color: '#f0f0f0' } })
      }
    },
    clearHighlight: clearHighlightInternal,
    pulseNode(id: string) {
      const node = nodesDs.current.get(id) as GraphNode | null
      if (!node) return
      const origSize = node.size as number
      const origColor = allNodeColors.current.get(id)
      let tick = 0
      const interval = setInterval(() => {
        tick++
        const expanded = tick % 2 === 1
        nodesDs.current.update({
          id,
          size: expanded ? origSize * 1.6 : origSize,
          color: expanded
            ? { background: '#bbf7d0', border: '#15803d', highlight: { background: '#86efac', border: '#166534' } }
            : origColor,
        })
        if (tick >= 6) {
          clearInterval(interval)
          nodesDs.current.update({ id, size: origSize, color: origColor })
        }
      }, 450)
    },
    getNetwork: () => networkRef.current,
  }))

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        backgroundImage: 'radial-gradient(circle, rgba(180,180,180,0.3) 1px, transparent 1px)',
        backgroundSize: '32px 32px',
        backgroundPosition: '0 0',
      }}
    />
  )
})
