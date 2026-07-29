import type { ActionPill } from '../../data/mock'

interface ActionPillsProps {
  pills: ActionPill[]
  onPillClick: (prompt: string) => void
}

export function ActionPills({ pills, onPillClick }: ActionPillsProps) {
  if (pills.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label="Contextual actions">
      {pills.map((pill) => (
        <button
          key={pill.id}
          type="button"
          onClick={() => onPillClick(pill.prompt)}
          className="focus-ring rounded-md border border-border-muted/30 bg-surface-raised px-2.5 py-1 text-xs font-medium text-text-secondary transition-all duration-instant hover:border-border-muted hover:text-text-primary hover:shadow-glow"
        >
          {pill.label}
        </button>
      ))}
    </div>
  )
}
