interface TextFieldProps {
  value: string
  placeholder?: string
  onChange: (value: string) => void
}

export function TextField({ value, placeholder, onChange }: TextFieldProps) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="focus-ring w-full rounded-xs border border-border-muted/20 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary"
    />
  )
}
