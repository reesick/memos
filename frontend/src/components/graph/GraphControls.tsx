interface Props {
  onFit: () => void
  onZoomIn: () => void
  onZoomOut: () => void
}

export function GraphControls({ onFit, onZoomIn, onZoomOut }: Props) {
  const btn = (label: string, title: string, onClick: () => void) => (
    <button
      key={label}
      title={title}
      onClick={onClick}
      style={{
        width: 30, height: 30,
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 5, fontSize: 14, cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: 'var(--text-secondary)',
        boxShadow: '0 1px 3px rgba(0,0,0,0.07)',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'var(--surface)')}
    >{label}</button>
  )

  return (
    <div style={{
      position: 'absolute', bottom: 16, right: 16,
      display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      {btn('⌂', 'Fit to screen (F)', onFit)}
      {btn('+', 'Zoom in', onZoomIn)}
      {btn('−', 'Zoom out', onZoomOut)}
    </div>
  )
}
