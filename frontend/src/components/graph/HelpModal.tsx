interface Props {
  onClose: () => void
  onReplayTour: () => void
}

const SHORTCUTS = [
  { key: 'F', desc: 'Fit graph to screen' },
  { key: 'Esc', desc: 'Deselect / close' },
  { key: '+  /  −', desc: 'Zoom in / out' },
  { key: '/', desc: 'Focus search box' },
]

export function HelpModal({ onClose, onReplayTour }: Props) {
  return (
    <>
      {/* Backdrop */}
      <div
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.25)', zIndex: 800 }}
        onClick={onClose}
      />

      {/* Panel */}
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        zIndex: 801, background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 10, padding: '22px 24px', width: 300,
        boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
        animation: 'fadeIn 0.15s ease',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>Keyboard shortcuts</span>
          <button
            onClick={onClose}
            style={{ width: 22, height: 22, border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 3 }}
          >×</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
          {SHORTCUTS.map(s => (
            <div key={s.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>{s.desc}</span>
              <kbd style={{
                fontFamily: 'var(--mono)', fontSize: 10, padding: '2px 7px',
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                borderRadius: 4, color: 'var(--text-secondary)',
              }}>{s.key}</kbd>
            </div>
          ))}
        </div>

        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          <button
            onClick={onReplayTour}
            style={{
              width: '100%', padding: '7px 0', fontSize: 12, fontWeight: 600,
              background: 'var(--accent-soft)', color: 'var(--accent)',
              border: '1px solid var(--accent)', borderRadius: 6, cursor: 'pointer',
              fontFamily: 'var(--font)',
            }}
          >
            Replay onboarding tour
          </button>
        </div>
      </div>
    </>
  )
}
