import type { InterviewPill } from '../../context/conversationalLoopTypes'

interface SmartActionPhasePillsProps {
  pills: InterviewPill[]
  onPillSelect: (pill: InterviewPill) => void
}

export function SmartActionPhasePills({ pills, onPillSelect }: SmartActionPhasePillsProps) {
  if (pills.length === 0) return null

  return (
    <div
      className="mb-2 flex flex-wrap gap-1.5"
      role="group"
      aria-label="Module interview actions"
    >
      {pills.map((pill) => (
        <button
          key={pill.id}
          type="button"
          onClick={() => onPillSelect(pill)}
          className={`focus-ring rounded-md border px-2.5 py-1 text-xs font-medium transition-all duration-instant hover:shadow-glow ${
            pill.fieldKey === '__run__' || pill.fieldKey === '__proceed__'
              ? 'border-border-muted/50 bg-border-muted text-white hover:opacity-90'
              : 'border-border-muted/30 bg-surface-raised text-text-secondary hover:border-border-muted hover:text-text-primary'
          }`}
        >
          {pill.label}
        </button>
      ))}
    </div>
  )
}
