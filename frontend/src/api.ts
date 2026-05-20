import type { AddResponse, AugmentResponse, HealthResponse, ListResponse, SearchResponse, ShouldInjectResponse } from './types'

const BASE = 'http://localhost:8000'

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, options)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  health: () => req<HealthResponse>('/health'),

  addMemory: (content: string, sessionId: string) =>
    req<AddResponse>('/memory/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, source_type: 'text', session_id: sessionId }),
    }),

  shouldInject: (prompt: string) =>
    req<ShouldInjectResponse>('/memory/should_inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    }),

  augment: (prompt: string, topK = 3) =>
    req<AugmentResponse>('/memory/augment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, top_k: topK }),
    }),

  listMemories: (limit = 50) =>
    req<ListResponse>(`/memory/list?limit=${limit}`),

  searchMemories: (query: string, topK = 20) =>
    req<SearchResponse>('/memory/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: topK }),
    }),

  deleteMemory: (memoryId: string) =>
    req<{ status: string }>(`/memory/${memoryId}`, { method: 'DELETE' }),

  getGraph: (entity: string, hops = 2) =>
    req<{ nodes: { id: string; name?: string; type: string }[]; edges: object[]; total_nodes: number; total_edges: number }>(
      `/memory/graph?entity=${encodeURIComponent(entity)}&hops=${hops}`
    ),
}
