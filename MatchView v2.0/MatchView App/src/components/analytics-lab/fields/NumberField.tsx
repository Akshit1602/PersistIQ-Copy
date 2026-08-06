interface NumberFieldProps {
  value: number
  min?: number
  max?: number
  step?: number
  placeholder?: string
  onChange: (value: number) => void
}

export function NumberField({
  value,
  min,
  max,
  step = 1,
  placeholder,
  onChange,
}: NumberFieldProps) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      onChange={(e) => onChange(Number(e.target.value))}
      className="focus-ring w-full rounded-xs border border-border-muted/20 bg-surface-base px-2.5 py-1.5 text-xs tabular-nums text-text-primary placeholder:text-text-secondary"
    />
  )
}
