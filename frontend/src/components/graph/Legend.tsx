export function LegendChips() {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
        <div style={{ width: 9, height: 9, borderRadius: '50%', background: '#dcfce7', border: '2px solid #16a34a', flexShrink: 0 }} />
        Entity
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#f5f5f5', border: '1px solid #d0d0d0', flexShrink: 0 }} />
        Fact
      </div>
    </div>
  )
}
