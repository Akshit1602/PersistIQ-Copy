import type { CSSProperties } from 'react'

interface NumericSliderFieldProps {
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  formatValue?: (value: number) => string
  'aria-label'?: string
}

export function NumericSliderField({
  value,
  min,
  max,
  step = 1,
  onChange,
  formatValue = (v) => String(v),
  'aria-label': ariaLabel,
}: NumericSliderFieldProps) {
  const clamped = Math.min(max, Math.max(min, value))
  const fillPct = max === min ? 0 : ((clamped - min) / (max - min)) * 100

  return (
    <div className="rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-2">
      <div className="flex items-center gap-3">
        <input
          type="range"
          className="numeric-slider min-w-0 flex-1"
          style={{ '--slider-fill': `${fillPct}%` } as CSSProperties}
          value={clamped}
          min={min}
          max={max}
          step={step}
          aria-label={ariaLabel}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <span className="min-w-[3rem] shrink-0 rounded-xs bg-surface-hover px-2 py-0.5 text-right text-xs font-medium tabular-nums text-text-primary">
          {formatValue(clamped)}
        </span>
      </div>
    </div>
  )
}
