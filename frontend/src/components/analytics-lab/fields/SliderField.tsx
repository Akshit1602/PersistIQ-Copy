interface SliderFieldProps {
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
}

export function SliderField({ value, min, max, step = 0.1, onChange }: SliderFieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <input
          type="range"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => onChange(Number(e.target.value))}
          className="min-w-0 flex-1 accent-border-muted"
        />
        <span className="w-11 shrink-0 rounded-md bg-surface-hover px-1.5 py-0.5 text-right text-xs tabular-nums font-medium text-text-primary">
          {value}%
        </span>
      </div>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="focus-ring w-24 rounded-xs border border-border-muted/20 bg-surface-base px-2 py-1 text-xs tabular-nums text-text-primary"
      />
    </div>
  )
}
