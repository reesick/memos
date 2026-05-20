import { useState } from 'react'

interface Props {
  onDone: () => void
}

const STEPS = [
  {
    title: 'This is your memory, visualized.',
    body: 'Green dots are entities — people or things MemoryOS remembers. Small gray dots are individual facts about them.',
    hint: 'Look at the canvas →',
    position: 'center' as const,
  },
  {
    title: 'Start by picking someone.',
    body: 'Click a name in the Start here list on the left to focus on what MemoryOS knows about them. Or type in the search box above it.',
    hint: '← Left rail',
    position: 'left' as const,
  },
  {
    title: 'Details live here.',
    body: 'Hover any dot for a quick preview. Click it to see everything in this panel. Click an entity name to focus the graph on them.',
    hint: 'This panel →',
    position: 'right' as const,
  },
]

export function OnboardingTour({ onDone }: Props) {
  const [step, setStep] = useState(0)
  const current = STEPS[step]

  function finish() {
    localStorage.setItem('memoryos.graph.onboarded', 'true')
    onDone()
  }

  function next() {
    if (step < STEPS.length - 1) {
      setStep(s => s + 1)
    } else {
      finish()
    }
  }

  const cardStyle = (): React.CSSProperties => {
    const base: React.CSSProperties = {
      position: 'fixed',
      zIndex: 1000,
      background: 'white',
      border: '1px solid #e5e7eb',
      borderRadius: 10,
      padding: '20px 22px',
      width: 300,
      boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
    }
    if (current.position === 'left') {
      return { ...base, top: '50%', left: 240, transform: 'translateY(-50%)' }
    }
    if (current.position === 'right') {
      return { ...base, top: '50%', right: 280, transform: 'translateY(-50%)' }
    }
    return { ...base, top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
  }

  return (
    <>
      {/* Dim overlay */}
      <div style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
        zIndex: 999, animation: 'fadeIn 0.2s ease',
      }} />

      {/* Tour card */}
      <div style={cardStyle()}>
        {/* Step indicator */}
        <div style={{ display: 'flex', gap: 5, marginBottom: 14 }}>
          {STEPS.map((_, i) => (
            <div
              key={i}
              style={{
                height: 3, flex: 1, borderRadius: 2,
                background: i <= step ? '#16a34a' : '#e5e7eb',
                transition: 'background 0.2s',
              }}
            />
          ))}
        </div>

        {/* Hint */}
        <div style={{ fontSize: 10, color: '#16a34a', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 8 }}>
          {current.hint}
        </div>

        {/* Content */}
        <div style={{ fontSize: 15, fontWeight: 700, color: '#111', marginBottom: 8, lineHeight: 1.35 }}>
          {current.title}
        </div>
        <div style={{ fontSize: 13, color: '#555', lineHeight: 1.6, marginBottom: 20 }}>
          {current.body}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button
            onClick={finish}
            style={{
              fontSize: 11, color: '#aaa', background: 'transparent', border: 'none',
              cursor: 'pointer', padding: 0, fontFamily: 'inherit',
            }}
          >
            Skip tour
          </button>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: '#aaa' }}>{step + 1} of {STEPS.length}</span>
            <button
              onClick={next}
              style={{
                padding: '7px 18px', fontSize: 12, fontWeight: 600,
                background: '#16a34a', color: 'white',
                border: 'none', borderRadius: 6, cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {step < STEPS.length - 1 ? 'Next →' : 'Got it'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
