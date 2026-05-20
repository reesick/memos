import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { GraphCanvas } from '../components/graph/GraphCanvas'
import type { GraphCanvasRef } from '../components/graph/GraphCanvas'
import { GraphLeftRail } from '../components/graph/GraphLeftRail'
import { GraphControls } from '../components/graph/GraphControls'
import { LegendChips } from '../components/graph/Legend'
import { RightInspector } from '../components/graph/RightInspector'
import { HoverTooltip } from '../components/graph/HoverTooltip'
import { Breadcrumb } from '../components/graph/Breadcrumb'
import { OnboardingTour } from '../components/graph/OnboardingTour'
import { HelpModal } from '../components/graph/HelpModal'
import { useGraphData } from '../hooks/useGraphData'
import type { GraphNode, GraphEdge } from '../hooks/useGraphData'
import { api } from '../api'

export function GraphPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const canvasRef = useRef<GraphCanvasRef>(null)

  const { data, loading, error, refresh } = useGraphData(10_000)

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [focusedEntity, setFocusedEntity] = useState<string | null>(searchParams.get('focus'))
  const [filteredNodeIds, setFilteredNodeIds] = useState<Set<string> | null>(null)
  const [displayNodes, setDisplayNodes] = useState<GraphNode[]>([])
  const [displayEdges, setDisplayEdges] = useState<GraphEdge[]>([])
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  const [showHelp, setShowHelp] = useState(false)
  const [showTour, setShowTour] = useState(false)
  const hasPulsed = useRef(false)
  // Ref mirror of focusedEntity so the searchParams effect never reads a stale closure value
  const focusedEntityRef = useRef<string | null>(searchParams.get('focus'))
  useEffect(() => { focusedEntityRef.current = focusedEntity }, [focusedEntity])

  // First-visit tour
  useEffect(() => {
    if (!localStorage.getItem('memoryos.graph.onboarded')) {
      setShowTour(true)
    }
  }, [])

  // Pulse most-connected entity after first load
  useEffect(() => {
    if (!data || hasPulsed.current || showTour) return
    const top = data.topEntities[0]
    if (!top) return
    const timer = setTimeout(() => {
      canvasRef.current?.pulseNode(`entity_${top.entity}`)
      hasPulsed.current = true
    }, 1600)
    return () => clearTimeout(timer)
  }, [data, showTour])

  // Sync display data when data or filters change
  useEffect(() => {
    if (!data) return
    if (filteredNodeIds) {
      const nodeSet = filteredNodeIds
      setDisplayNodes(data.nodes.filter(n => nodeSet.has(n.id)))
      setDisplayEdges(data.edges.filter(e => nodeSet.has(e.from as string) && nodeSet.has(e.to as string)))
    } else {
      setDisplayNodes(data.nodes)
      setDisplayEdges(data.edges)
    }
  }, [data, filteredNodeIds])

  // Handle ?focus= param — use ref to avoid stale closure on focusedEntity
  useEffect(() => {
    const f = searchParams.get('focus')
    if (f && f !== focusedEntityRef.current) {
      handleFocusEntity(f, 2)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'f' || e.key === 'F') canvasRef.current?.fit()
      if (e.key === 'Escape') {
        setSelectedNode(null)
        canvasRef.current?.clearHighlight()
        setShowHelp(false)
      }
      if (e.key === '+' || e.key === '=') canvasRef.current?.zoomIn()
      if (e.key === '-') canvasRef.current?.zoomOut()
      if (e.key === '/') {
        e.preventDefault()
        document.getElementById('graph-search')?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  async function handleFocusEntity(entity: string, hops: number) {
    console.log(`[GraphPage] FOCUS → entity="${entity}" hops=${hops} | prev focusedEntity="${focusedEntity}"`)
    setFocusedEntity(entity)
    setSearchParams({ focus: entity })
    try {
      const g = await api.getGraph(entity, hops)
      console.log(`[GraphPage] FOCUS api.getGraph returned ${g.nodes.length} nodes, ${g.edges?.length ?? 0} edges`)
      if (g.nodes.length === 0 || !data) {
        const entityId = `entity_${entity}`
        const edges = data?.edges.filter(e => e.from === entityId || e.to === entityId) ?? []
        const connectedIds = new Set([entityId, ...edges.map(e => e.to as string), ...edges.map(e => e.from as string)])
        setFilteredNodeIds(connectedIds)
      } else {
        const ids = new Set<string>()
        for (const n of g.nodes) {
          if (n.type === 'Fact') ids.add(n.id as string)
          else ids.add(`entity_${n.name ?? n.id}`)
        }
        ids.add(`entity_${entity}`)
        setFilteredNodeIds(ids)
      }
    } catch (err) {
      console.warn('[GraphPage] FOCUS api.getGraph failed, falling back to local edges', err)
      if (data) {
        const entityId = `entity_${entity}`
        const edges = data.edges.filter(e => e.from === entityId || e.to === entityId)
        const connectedIds = new Set([entityId, ...edges.map(e => e.to as string), ...edges.map(e => e.from as string)])
        setFilteredNodeIds(connectedIds)
      }
    }
    setTimeout(() => canvasRef.current?.fit(), 600)
  }

  function handleClearFocus() {
    console.log(`[GraphPage] CLEAR FOCUS | was="${focusedEntity}"`)
    setFocusedEntity(null)
    setSearchParams({})
    setFilteredNodeIds(null)
    setTimeout(() => canvasRef.current?.fit(), 300)
  }

  function handleSearch(q: string) {
    if (!q || !data) {
      canvasRef.current?.clearHighlight()
      return
    }
    const lower = q.toLowerCase()
    const matchIds = new Set<string>()
    for (const n of data.nodes) {
      if (
        String(n.label).toLowerCase().includes(lower) ||
        String(n.attribute ?? '').toLowerCase().includes(lower) ||
        String(n.value ?? '').toLowerCase().includes(lower) ||
        String(n.session_id ?? '').toLowerCase().includes(lower) ||
        String(n.entity ?? '').toLowerCase().includes(lower)
      ) {
        matchIds.add(n.id)
        if (n.group === 'fact' && n.entity) matchIds.add(`entity_${n.entity}`)
      }
    }
    canvasRef.current?.highlightNodes(matchIds)
    setTimeout(() => canvasRef.current?.fit(), 200)
  }

  const handleFilterChange = useCallback((sourceTypes: string[]) => {
    if (!data) return
    if (sourceTypes.length === 0) {
      canvasRef.current?.clearHighlight()
      return
    }
    const matchIds = new Set<string>()
    for (const n of data.nodes) {
      if (n.group === 'entity') { matchIds.add(n.id); continue }
      if (!sourceTypes.includes(n.source_type || '')) continue
      matchIds.add(n.id)
      if (n.entity) matchIds.add(`entity_${n.entity}`)
    }
    canvasRef.current?.highlightNodes(matchIds)
  }, [data])

  function handleNodeDeleted(_memoryId: string) {
    setSelectedNode(null)
    refresh()
  }

  function handleSelectNode(node: GraphNode | null) {
    setSelectedNode(node)
  }

  if (error) {
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)', gap: 12 }}>
        <div style={{ fontSize: 13, color: 'var(--danger)' }}>API unreachable — is the server running?</div>
        <button onClick={refresh} style={{ padding: '6px 16px', background: 'var(--text-primary)', color: 'white', border: 'none', borderRadius: 5, cursor: 'pointer', fontSize: 12 }}>Retry</button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>

      {/* ── Top bar ── */}
      <div style={{
        height: 44, background: 'var(--surface)', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', padding: '0 16px', gap: 12, flexShrink: 0, zIndex: 100,
      }}>
        <button
          onClick={() => navigate('/')}
          style={{
            display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, fontWeight: 500,
            color: 'var(--text-secondary)', background: 'transparent', border: 'none', cursor: 'pointer',
            padding: '4px 8px', borderRadius: 5,
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >
          ← Back to chat
        </button>

        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />

        <div style={{ fontWeight: 600, fontSize: 14, letterSpacing: '-0.01em', display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} />
          Knowledge Graph
        </div>

        <Breadcrumb focusedEntity={focusedEntity} onClearFocus={handleClearFocus} />

        <div style={{ flex: 1 }} />

        <LegendChips />

        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />

        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
          {data
            ? `${data.nodes.filter(n => n.group === 'entity').length} entities · ${data.nodes.filter(n => n.group === 'fact').length} facts`
            : 'loading…'}
        </span>

        <button
          onClick={() => setShowHelp(true)}
          title="Keyboard shortcuts & help"
          style={{
            width: 26, height: 26, border: '1px solid var(--border)', background: 'var(--surface-2)',
            borderRadius: 5, cursor: 'pointer', fontSize: 12, color: 'var(--text-muted)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'var(--surface-2)')}
        >?</button>
      </div>

      {/* ── Main body ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left rail */}
        <GraphLeftRail
          data={data}
          onSearch={handleSearch}
          onFocusEntity={handleFocusEntity}
          onFilterChange={handleFilterChange}
        />

        {/* Canvas area */}
        <div
          style={{ flex: 1, position: 'relative', overflow: 'hidden' }}
          id="tour-canvas"
          onMouseMove={e => setMousePos({ x: e.clientX, y: e.clientY })}
          onMouseLeave={() => setHoveredNode(null)}
        >
          {/* Loading overlay */}
          {loading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--surface-2)', zIndex: 10,
            }}>
              <div style={{ display: 'flex', gap: 6 }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{
                    width: 7, height: 7, borderRadius: '50%', background: 'var(--accent)',
                    animation: `pulse 1.2s ease-in-out ${i * 0.3}s infinite`,
                  }} />
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!loading && data && data.nodes.length === 0 && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 12,
            }}>
              <div style={{ width: 12, height: 12, borderRadius: '50%', background: 'var(--accent)', opacity: 0.4 }} />
              <div style={{ fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.6 }}>
                No memories yet.<br />
                <span
                  onClick={() => navigate('/')}
                  style={{ color: 'var(--accent)', cursor: 'pointer', textDecoration: 'underline' }}
                >Start a conversation</span> to grow your graph.
              </div>
            </div>
          )}

          {/* Graph canvas */}
          {data && (
            <GraphCanvas
              ref={canvasRef}
              nodes={displayNodes}
              edges={displayEdges}
              onSelectNode={handleSelectNode}
              onHoverNode={setHoveredNode}
            />
          )}

          {/* Hover tooltip */}
          <HoverTooltip node={hoveredNode} x={mousePos.x} y={mousePos.y} data={data} />

          {/* Zoom controls */}
          <GraphControls
            onFit={() => canvasRef.current?.fit()}
            onZoomIn={() => canvasRef.current?.zoomIn()}
            onZoomOut={() => canvasRef.current?.zoomOut()}
          />

          {/* Keyboard hint */}
          <div style={{
            position: 'absolute', bottom: 16, left: 16,
            fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--mono)',
            lineHeight: 1.7,
          }}>
            F fit · / search · Esc deselect · +/− zoom
          </div>
        </div>

        {/* Right inspector */}
        <RightInspector
          node={selectedNode}
          data={data}
          onClose={() => { setSelectedNode(null); canvasRef.current?.clearHighlight() }}
          onDeleted={handleNodeDeleted}
          onFocusEntity={(entity) => handleFocusEntity(entity, 2)}
          onClearFocus={handleClearFocus}
          focusedEntity={focusedEntity}
        />
      </div>

      {/* Onboarding tour */}
      {showTour && (
        <OnboardingTour onDone={() => setShowTour(false)} />
      )}

      {/* Help modal */}
      {showHelp && (
        <HelpModal
          onClose={() => setShowHelp(false)}
          onReplayTour={() => {
            setShowHelp(false)
            localStorage.removeItem('memoryos.graph.onboarded')
            setShowTour(true)
          }}
        />
      )}
    </div>
  )
}
