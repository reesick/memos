export interface Memory {
  memory_id: string
  entity: string
  attribute: string
  value: string
  source_type: string
  session_id: string
  timestamp: number
  expired_at?: string | null
  score?: number
}

export interface HealthResponse {
  status: string
  version: string
  ollama: boolean
}

export interface AddResponse {
  facts_extracted: number
  facts_added: number
  memory_ids: string[]
}

export interface SearchResponse {
  results: Memory[]
}

export interface ListResponse {
  total: number
  memories: Memory[]
}

export interface AugmentResponse {
  augmented_prompt: string
  injected: boolean
  injection_reason: string
}

export interface ShouldInjectResponse {
  inject: boolean
  check_ms: number
}

export interface GraphNode {
  id: string
  label: string
  title?: string
  group: 'entity' | 'fact'
}

export interface GraphEdge {
  id: string
  from: string
  to: string
  label?: string
}

export interface ChatMessage {
  id: string
  role: 'you' | 'ai'
  text: string
  isContext?: boolean
}
