import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'

export function TopBar() {
  const [online, setOnline] = useState(true)
  const [model, setModel] = useState('claude')
  const location = useLocation()
  const navigate = useNavigate()
  const onGraph = location.pathname === '/graph'

  useEffect(() => {
    api.health()
      .then(d => { setModel(d.ollama ? 'ollama' : 'claude'); setOnline(true) })
      .catch(() => setOnline(false))
  }, [])

  return (
    <div style={{
      height: 44, background: 'var(--surface)', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', padding: '0 16px', gap: 12,
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
    }}>
      {/* Logo — always navigates home */}
      <div
        onClick={() => navigate('/')}
        style={{ fontWeight: 600, fontSize: 14, letterSpacing: '-0.01em', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
      >
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} />
        MemoryOS
      </div>

      {/* Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
        <div style={{
          width: 7, height: 7, borderRadius: '50%',
          background: online ? 'var(--accent)' : 'var(--danger)',
          animation: online ? 'pulse 2.4s ease-in-out infinite' : 'none',
        }} />
        <span>{online ? 'recording conversation' : 'API offline'}</span>
      </div>

      <div style={{ flex: 1 }} />

      {/* Graph nav link (only on main page) */}
      {!onGraph && (
        <button
          onClick={() => navigate('/graph')}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)',
            background: 'var(--surface-2)', border: '1px solid var(--border)',
            borderRadius: 5, padding: '4px 10px', cursor: 'pointer',
            transition: 'all 0.1s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-soft)'; e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="2" cy="2" r="1.5" fill="currentColor" />
            <circle cx="10" cy="2" r="1.5" fill="currentColor" />
            <circle cx="6" cy="10" r="1.5" fill="currentColor" />
            <line x1="2" y1="2" x2="10" y2="2" stroke="currentColor" strokeWidth="1" />
            <line x1="2" y1="2" x2="6" y2="10" stroke="currentColor" strokeWidth="1" />
            <line x1="10" y1="2" x2="6" y2="10" stroke="currentColor" strokeWidth="1" />
          </svg>
          Graph
        </button>
      )}

      {/* Model badge */}
      <div style={{
        fontSize: 11, color: 'var(--text-muted)', background: 'var(--surface-2)',
        border: '1px solid var(--border)', borderRadius: 4, padding: '2px 8px',
        fontFamily: 'var(--mono)',
      }}>
        {model}
      </div>
    </div>
  )
}
