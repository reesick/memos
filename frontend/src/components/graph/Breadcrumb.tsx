interface Props {
  focusedEntity: string | null
  onClearFocus: () => void
}

export function Breadcrumb({ focusedEntity, onClearFocus }: Props) {
  if (!focusedEntity) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>▸</span>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        background: 'var(--accent-soft)', border: '1px solid var(--accent)',
        borderRadius: 4, padding: '2px 6px 2px 8px',
      }}>
        <span style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 500 }}>
          Focus: {focusedEntity}
        </span>
        <button
          onClick={onClearFocus}
          title="Clear focus"
          style={{
            width: 16, height: 16, border: 'none', background: 'transparent',
            cursor: 'pointer', color: 'var(--accent)', fontSize: 12,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: 2, padding: 0,
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(22,163,74,0.15)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >×</button>
      </div>
    </div>
  )
}
