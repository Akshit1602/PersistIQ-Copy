interface ToggleFieldProps {
  label: string
  value: boolean
  description?: string
  onChange: (value: boolean) => void
}

export function ToggleField({ label, value, description, onChange }: ToggleFieldProps) {
  return (
    <div className="flex items-start justify-between gap-2.5 rounded-xs border border-border-muted/15 bg-surface-base px-2.5 py-2">
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-text-primary">{label}</p>
        {description && (
          <p className="mt-0.5 text-micro leading-relaxed text-text-secondary">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`focus-ring relative h-4 w-7 shrink-0 rounded-full transition-colors duration-instant ${
          value ? 'bg-border-muted' : 'bg-border-muted/25'
        }`}
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform duration-instant ${
            value ? 'translate-x-3.5' : 'translate-x-0.5'
          }`}
        />
      </button>
    </div>
  )
}
