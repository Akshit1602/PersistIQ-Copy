interface SelectFieldProps {
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}

export function SelectField({ value, options, onChange }: SelectFieldProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="focus-ring w-full rounded-xs border border-border-muted/20 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary"
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}
