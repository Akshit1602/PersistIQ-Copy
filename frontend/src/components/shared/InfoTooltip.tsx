import { Info } from 'lucide-react'
import { AppIcon } from './AppIcon'

interface Props {
  text: string
}

/** A small (i) icon that reveals explanatory text on hover/focus — used to
 * move long narrative prose out of the main flow and into an on-demand
 * tooltip, per the "clean KPI cards, narrative in info modals" pattern. */
export function InfoTooltip({ text }: Props) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-text-secondary hover:text-border-muted"
        aria-label="More information"
      >
        <AppIcon icon={Info} size="xs" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-30 mt-1 w-[220px] rounded-xs border border-border-muted/20 bg-text-primary px-2 py-1.5 text-micro leading-relaxed text-white opacity-0 shadow-md group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  )
}
