import { useEffect, useState } from 'react'

interface SynthesisProgressOverlayProps {
  active: boolean
  /** Duration in ms (default random 5–8s). */
  durationMs?: number
  title?: string
  subtitle?: string
  onComplete: () => void
}

const DEFAULT_STEPS = [
  'Reading hypothesis & goals…',
  'Sizing opportunity signals…',
  'Classifying metrics & directions…',
  'Deriving experiment design…',
  'Assembling digital experiment brief…',
]

export function SynthesisProgressOverlay({
  active,
  durationMs,
  title = 'Synthesizing experiment setup',
  subtitle = 'Deriving design type and building your brief…',
  onComplete,
}: SynthesisProgressOverlayProps) {
  const [progress, setProgress] = useState(0)
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    if (!active) {
      setProgress(0)
      setStepIndex(0)
      return
    }

    const total =
      durationMs ?? 5000 + Math.floor(Math.random() * 3001) /* 5–8s */
    const started = performance.now()
    let frame = 0
    let completed = false

    const tick = (now: number) => {
      const elapsed = now - started
      const next = Math.min(100, (elapsed / total) * 100)
      setProgress(next)
      setStepIndex(
        Math.min(
          DEFAULT_STEPS.length - 1,
          Math.floor((next / 100) * DEFAULT_STEPS.length),
        ),
      )
      if (next >= 100) {
        if (!completed) {
          completed = true
          onComplete()
        }
        return
      }
      frame = requestAnimationFrame(tick)
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [active, durationMs, onComplete])

  if (!active) return null

  return (
    <div
      className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-surface-raised/95 px-6 backdrop-blur-[2px]"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="w-full max-w-sm">
        <p className="text-center text-sm font-semibold text-text-primary">{title}</p>
        <p className="mt-1 text-center text-xs text-text-secondary">{subtitle}</p>

        <div className="mt-5 space-y-2">
          <div className="h-3 w-full animate-pulse rounded-xs bg-border-muted/15" />
          <div
            className="h-3 animate-pulse rounded-xs bg-border-muted/10"
            style={{ width: '80%' }}
          />
          <div
            className="h-3 animate-pulse rounded-xs bg-border-muted/10"
            style={{ width: '60%' }}
          />
        </div>

        <div className="mt-5">
          <div className="mb-1.5 flex items-center justify-between text-micro text-text-secondary">
            <span>{DEFAULT_STEPS[stepIndex]}</span>
            <span className="tabular-nums">{Math.round(progress)}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-xs bg-border-muted/20">
            <div
              className="h-full rounded-xs bg-border-muted transition-[width] duration-100 ease-linear"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
