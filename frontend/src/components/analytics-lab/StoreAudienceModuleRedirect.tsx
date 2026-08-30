import { ArrowRight, Info } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'

/**
 * The generic Analytics Lab module list still has an "Audience Selection"
 * entry (relabeled "Store Matching & Panel Selection" for store experiments
 * via ModuleConfigForm's displayLabel). Rather than duplicate a second
 * schema-driven form here, this redirects into the real StorePanelMatchingWizard
 * component (the same one opened from the brief handoff card), so there's
 * only one implementation of store matching, not two.
 */
export function StoreAudienceModuleRedirect() {
  const { openAudienceWizard } = useMatchView()

  return (
    <div className="flex min-h-0 flex-1 flex-col items-start gap-3 px-1 py-2">
      <div className="flex items-start gap-2 rounded-xs border border-border-muted/20 bg-surface-hover/50 px-3 py-2.5">
        <AppIcon icon={Info} size="sm" className="mt-0.5 shrink-0 text-border-muted" />
        <p className="text-xs text-text-secondary leading-relaxed">
          Store experiments use the dedicated Store Matching & Panel Selection wizard — Composite
          Distance matching, spatial buffer masking, and the pairwise donor panel table all live there
          rather than in this generic form.
        </p>
      </div>
      <button
        type="button"
        onClick={() => openAudienceWizard()}
        className="focus-ring flex items-center gap-1.5 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90"
      >
        Open Store Matching & Panel Selection
        <AppIcon icon={ArrowRight} size="xs" />
      </button>
    </div>
  )
}
