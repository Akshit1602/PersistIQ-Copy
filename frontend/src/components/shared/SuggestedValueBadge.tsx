import { Sparkles, Undo2 } from 'lucide-react'
import type { FieldSuggestion } from '../../data/inputSuggestions'
import { AppIcon } from './AppIcon'
import { InfoTooltip } from './InfoTooltip'

interface Props {
  suggestion: FieldSuggestion
  /** Current field value — decides "applied" vs "apply this" framing. */
  value: unknown
  onApply: (value: unknown) => void
  /** Restores the pre-suggestion value; omit to hide the revert control. */
  onRevert?: () => void
  formatValue?: (value: unknown) => string
}

const SOURCE_TONE: Record<FieldSuggestion['source'], string> = {
  dataset: 'text-emerald-700 border-emerald-600/25 bg-emerald-500/5',
  'prior-run': 'text-sky-700 border-sky-600/25 bg-sky-500/5',
  hypothesis: 'text-sky-700 border-sky-600/25 bg-sky-500/5',
  derived: 'text-sky-700 border-sky-600/25 bg-sky-500/5',
  'project-history': 'text-sky-700 border-sky-600/25 bg-sky-500/5',
  benchmark: 'text-amber-700 border-amber-600/25 bg-amber-500/5',
}

function defaultFormat(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'number') return String(value)
  return String(value ?? '')
}

function sameValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => String(item) === String(b[i]))
  }
  if (typeof a === 'number' || typeof b === 'number') return Number(a) === Number(b)
  return String(a ?? '') === String(b ?? '')
}

/**
 * Provenance for one field: where the value came from, why, and a one-click way
 * to take it (or put it back). Rendered only when a suggestion exists — a field
 * with nothing behind it shows no badge rather than a hollow "auto-detected".
 */
export function SuggestedValueBadge({ suggestion, value, onApply, onRevert, formatValue }: Props) {
  const format = formatValue ?? defaultFormat
  const applied = sameValue(value, suggestion.value)
  const tone = SOURCE_TONE[suggestion.source]
  const period = suggestion.asOf ? ` · ${suggestion.asOf}` : ''

  return (
    <div className="mt-1 flex items-center gap-1">
      <span
        className={`inline-flex items-center gap-1 rounded-xs border px-1.5 py-0.5 text-micro font-medium ${tone}`}
      >
        <AppIcon icon={Sparkles} size="xs" />
        {applied ? suggestion.label : `Suggested ${format(suggestion.value)} — ${suggestion.label}`}
      </span>

      <InfoTooltip text={`${suggestion.rationale}${period}`} />

      {applied ? (
        onRevert ? (
          <button
            type="button"
            onClick={onRevert}
            className="focus-ring inline-flex items-center gap-0.5 rounded-xs px-1 py-0.5 text-micro text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
            title="Revert to the previous value"
          >
            <AppIcon icon={Undo2} size="xs" />
            Undo
          </button>
        ) : null
      ) : (
        <button
          type="button"
          onClick={() => onApply(suggestion.value)}
          className="focus-ring rounded-xs px-1 py-0.5 text-micro font-medium text-text-secondary underline-offset-2 transition-colors hover:bg-surface-hover hover:text-text-primary hover:underline"
          title={`Apply ${format(suggestion.value)}`}
        >
          Use it
        </button>
      )}
    </div>
  )
}
