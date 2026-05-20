import type { Memory } from '../types'

const STATIC_ATTRS = ['role', 'name', 'university', 'employer', 'location', 'degree']

interface Props {
  memories: Memory[]
  sessionId: string
  sessionStart: Date
  factsAdded: number
}

export function RightPanel({ memories, sessionId, sessionStart, factsAdded }: Props) {
  const staticFacts = memories.filter(m => STATIC_ATTRS.some(a => (m.attribute || '').includes(a)))
  const dynFacts = memories.filter(m => !STATIC_ATTRS.some(a => (m.attribute || '').includes(a)))

  function renderFacts(facts: Memory[]) {
    if (!facts.length) return <div style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>None yet.</div>
    return facts.slice(0, 6).map(m => {
      const val = (() => { const v = String(m.value ?? ''); return v.length > 50 ? v.slice(0, 50) + '…' : v })()
      return (
        <div key={m.memory_id} style={{ padding: '5px 0', fontSize: 12, color: 'var(--text-primary)', borderBottom: '1px solid var(--border)', lineHeight: 1.4 }}>
          <em style={{ color: 'var(--accent)', fontStyle: 'normal', fontWeight: 500 }}>{m.entity || '–'}</em>
          {' · '}{(m.attribute || '').replace(/_/g, ' ')}: {val}
        </div>
      )
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--surface)', height: '100%' }}>
      {/* Header */}
      <div style={{ height: 40, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 16px' }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Profile</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Static</div>
          {renderFacts(staticFacts)}
        </div>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Dynamic</div>
          {renderFacts(dynFacts)}
        </div>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Session</div>
          {[
            { label: 'Session ID', value: sessionId.slice(-8), mono: true },
            { label: 'Facts added', value: String(factsAdded), mono: true },
            { label: 'Started', value: sessionStart.toLocaleTimeString() },
          ].map(row => (
            <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 11 }}>
              <span style={{ color: 'var(--text-muted)' }}>{row.label}</span>
              <span style={{ color: 'var(--text-primary)', fontFamily: row.mono ? 'var(--mono)' : 'var(--font)', fontSize: 10 }}>{row.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
