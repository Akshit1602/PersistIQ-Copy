import { ShieldCheck, AlertTriangle } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import type { ControlPanelResult } from '../../data/storePanelMatching'

interface Props {
  experimentKey: string
}

export function StoreMatchingInsights({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['audience-selection']?.lastResult as ControlPanelResult | undefined

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Generate the Control Store Panel from Store Matching & Panel Selection to see the pairwise donor
        panel table here.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="type-overline">Pairwise & Donor Panel</p>
          <span className="text-micro text-text-secondary">
            {result.totalPairs.toLocaleString()} pairs \u00B7 avg SMD {result.averageSmd.toFixed(3)}
            {result.overlapWarningCount > 0 && (
              <span className="ml-1.5 text-amber-700"> \u00B7 {result.overlapWarningCount} overlap warning{result.overlapWarningCount > 1 ? 's' : ''}</span>
            )}
          </span>
        </div>
        <div className="max-h-72 overflow-y-auto rounded-xs border border-border-muted/20">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface-hover/90">
              <tr>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Test Store</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Control Match</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Confidence</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">SMD</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Spatial Buffer</th>
              </tr>
            </thead>
            <tbody>
              {result.pairs.slice(0, 50).map((pair) => (
                <tr key={pair.testStoreId} className="border-t border-border-muted/15">
                  <td className="px-2.5 py-1.5 text-text-primary">{pair.testStoreLabel}</td>
                  <td className="px-2.5 py-1.5 text-text-secondary">{pair.controlStoreLabel}</td>
                  <td className="px-2.5 py-1.5 tabular-nums">
                    <span className={pair.matchConfidencePercent >= 90 ? 'text-green-700' : 'text-amber-700'}>
                      {pair.matchConfidencePercent.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-2.5 py-1.5 tabular-nums text-text-primary">
                    {pair.smd.toFixed(2)} <span className="text-micro text-text-secondary">({pair.smdQuality})</span>
                  </td>
                  <td className="px-2.5 py-1.5">
                    {pair.spatialBufferStatus === 'clear' ? (
                      <span className="flex items-center gap-1 text-green-700">
                        <AppIcon icon={ShieldCheck} size="xs" /> Clear
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-amber-700">
                        <AppIcon icon={AlertTriangle} size="xs" /> Overlap
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {result.pairs.length > 50 && (
          <p className="mt-1.5 text-micro text-text-secondary">Showing 50 of {result.pairs.length.toLocaleString()} matched pairs.</p>
        )}
      </div>
    </div>
  )
}
