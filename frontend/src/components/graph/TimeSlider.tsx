import { useEffect, useRef, useState } from 'react'

interface Props {
  oldestTs: number
  newestTs: number
  onChange: (cutoffTs: number) => void
  onReset: () => void
}

export function TimeSlider({ oldestTs, newestTs, onChange, onReset }: Props) {
  const [value, setValue] = useState(newestTs)
  const [playing, setPlaying] = useState(false)
  const [active, setActive] = useState(false)
  const rafRef = useRef<number | null>(null)
  const startRef = useRef(0)
  const range = newestTs - oldestTs || 1

  useEffect(() => {
    setValue(newestTs)
  }, [newestTs])

  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      return
    }
    const duration = 10_000 // 10s playback
    const startValue = oldestTs
    startRef.current = performance.now()

    function tick(now: number) {
      const elapsed = now - startRef.current
      const progress = Math.min(elapsed / duration, 1)
      const current = startValue + progress * range
      setValue(current)
      onChange(current)
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        setPlaying(false)
      }
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [playing, oldestTs, range, onChange])

  function handleScrub(v: number) {
    if (playing) { setPlaying(false); if (rafRef.current) cancelAnimationFrame(rafRef.current) }
    setValue(v)
    setActive(v < newestTs)
    if (v < newestTs) onChange(v)
    else onReset()
  }

  function handlePlayPause() {
    if (!playing) {
      setValue(oldestTs)
      setActive(true)
      onChange(oldestTs)
    }
    setPlaying(p => !p)
  }

  function handleReset() {
    setPlaying(false)
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    setValue(newestTs)
    setActive(false)
    onReset()
  }

  const pct = ((value - oldestTs) / range) * 100
  const asOf = active ? new Date(value * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'now'

  return (
    <div style={{
      padding: '10px 14px 12px',
      borderTop: '1px solid var(--border)',
      background: 'var(--surface)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
          Time travel
        </span>
        <span style={{
          fontSize: 10, fontFamily: 'var(--mono)', color: active ? 'var(--accent)' : 'var(--text-muted)',
          marginLeft: 'auto',
        }}>
          {asOf}
        </span>
      </div>

      <input
        type="range"
        min={oldestTs}
        max={newestTs}
        step={(range) / 500}
        value={value}
        onChange={e => handleScrub(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer', marginBottom: 8 }}
      />

      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={handlePlayPause}
          style={{
            flex: 1, padding: '4px 0', fontSize: 11, fontWeight: 600,
            background: playing ? 'var(--accent)' : 'var(--text-primary)',
            color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer',
            fontFamily: 'var(--font)',
          }}
        >
          {playing ? '⏸ Pause' : '▶ Play'}
        </button>
        {active && (
          <button
            onClick={handleReset}
            style={{
              padding: '4px 10px', fontSize: 11, fontWeight: 600,
              background: 'transparent', color: 'var(--text-muted)',
              border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer',
              fontFamily: 'var(--font)',
            }}
          >
            Reset
          </button>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
        <span>{new Date(oldestTs * 1000).toLocaleDateString()}</span>
        <span style={{ background: '#f0fdf4', color: 'var(--accent)', padding: '0 4px', borderRadius: 2 }}>
          {Math.round(pct)}%
        </span>
        <span>now</span>
      </div>
    </div>
  )
}
