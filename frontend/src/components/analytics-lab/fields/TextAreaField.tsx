interface TextAreaFieldProps {
  value: string
  placeholder?: string
  rows?: number
  onChange: (value: string) => void
}

export function TextAreaField({
  value,
  placeholder,
  rows = 4,
  onChange,
}: TextAreaFieldProps) {
  return (
    <textarea
      value={value}
      rows={rows}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="focus-ring w-full resize-y rounded-xs border border-border-muted/20 bg-surface-base px-2.5 py-1.5 text-xs leading-relaxed text-text-primary placeholder:text-text-secondary"
    />
  )
}
