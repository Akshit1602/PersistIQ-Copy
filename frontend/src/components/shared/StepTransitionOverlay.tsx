import { useEffect, useRef } from 'react'
import { MatchViewSpinner } from './MatchViewSpinner'

interface StepTransitionOverlayProps {
  active: boolean
  /** Hold duration in ms. Defaults to a random 2–3s. */
  durationMs?: number
  title?: string
  subtitle?: string
  onComplete: () => void
}

export function StepTransitionOverlay({
  active,
  durationMs,
  title = 'Loading next step',
  subtitle = 'Preparing your inputs…',
  onComplete,
}: StepTransitionOverlayProps) {
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    if (!active) return

    const total = durationMs ?? 2000 + Math.floor(Math.random() * 1001)
    const timer = window.setTimeout(() => {
      onCompleteRef.current()
    }, total)

    return () => window.clearTimeout(timer)
  }, [active, durationMs])

  if (!active) return null

  return (
    <div
      className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-surface-raised/92 px-6 backdrop-blur-[2px]"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <MatchViewSpinner className="h-[72px] w-[86px]" label={title} />
      <p className="mt-5 text-center text-sm font-semibold text-text-primary">{title}</p>
      <p className="mt-1 text-center text-xs text-text-secondary">{subtitle}</p>
    </div>
  )
}
