import { useState, useCallback } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { TopBar } from './components/TopBar'
import { ChatPanel } from './components/ChatPanel'
import { MemoriesPanel } from './components/MemoriesPanel'
import { RightPanel } from './components/RightPanel'
import { GraphPage } from './pages/GraphPage'
import type { Memory } from './types'

function makeSessionId() { return 'sess_' + Date.now() }

function MainApp() {
  const [sessionId, setSessionId] = useState(makeSessionId)
  const [sessionStart, setSessionStart] = useState(() => new Date())
  const [factsAdded, setFactsAdded] = useState(0)
  const [refreshKey, setRefreshKey] = useState(0)
  const [memories, setMemories] = useState<Memory[]>([])

  const handleFactsAdded = useCallback((n: number) => setFactsAdded(prev => prev + n), [])
  const handleMemoriesChanged = useCallback(() => setRefreshKey(k => k + 1), [])
  const handleClear = useCallback(() => {
    setSessionId(makeSessionId())
    setSessionStart(new Date())
    setFactsAdded(0)
  }, [])
  const handleMemoriesLoaded = useCallback((mems: Memory[]) => setMemories(mems), [])

  return (
    <>
      <TopBar />
      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr 300px', height: '100vh', paddingTop: 44 }}>
        <ChatPanel
          sessionId={sessionId}
          onFactsAdded={handleFactsAdded}
          onMemoriesChanged={handleMemoriesChanged}
          onClear={handleClear}
        />
        <MemoriesPanel refreshKey={refreshKey} onMemoriesLoaded={handleMemoriesLoaded} />
        <RightPanel memories={memories} sessionId={sessionId} sessionStart={sessionStart} factsAdded={factsAdded} />
      </div>
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainApp />} />
        <Route path="/graph" element={<GraphPage />} />
      </Routes>
    </BrowserRouter>
  )
}
