import { Wifi, CheckCircle2, AlertTriangle, PackageX } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import type { StoreFeedDiagnosticsResult } from '../../data/storeMonitoring'

interface Props {
  experimentKey: string
}

export function StoreFeedInsights({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['experiment-analysis']?.lastResult as StoreFeedDiagnosticsResult | undefined

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run Store Feed & Execution Diagnostics from the module panel to see live feed status here.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        {result.posIngestionPercent !== null && (
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <AppIcon icon={Wifi} size="sm" className="text-border-muted" />
              <p className="type-overline">POS Ingestion Status</p>
            </div>
            <p className={`text-xl font-bold tabular-nums ${result.posIngestionPercent >= 99 ? 'text-green-600' : 'text-amber-700'}`}>
              {result.posIngestionPercent.toFixed(1)}%
            </p>
            {result.storesWithDataGaps > 0 && (
              <p className="mt-0.5 text-micro text-amber-700">{result.storesWithDataGaps} store(s) with data gaps</p>
            )}
          </div>
        )}
        {result.operationalExecutionRatePercent !== null && (
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
            <p className="type-overline mb-1">Operational Execution Rate</p>
            <p className={`text-xl font-bold tabular-nums ${result.operationalExecutionRatePercent >= 92 ? 'text-green-600' : 'text-amber-700'}`}>
              {result.operationalExecutionRatePercent.toFixed(1)}%
            </p>
          </div>
        )}
      </div>

      {result.stockoutFlags !== null && result.stockoutFlags.length > 0 && (
        <div className="rounded-[8px] border border-amber-500/25 bg-amber-50/40 px-4 py-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-amber-800">
            <AppIcon icon={PackageX} size="xs" /> Stockout Velocity Alerts ({result.stockoutFlags.length})
          </p>
          <ul className="mt-1.5 space-y-0.5">
            {result.stockoutFlags.map((f) => (
              <li key={f.storeId} className="text-micro text-amber-800">Store #{f.storeId} — {f.reason}</li>
            ))}
          </ul>
        </div>
      )}

      {result.quarantineCandidates !== null && result.quarantineCandidates.length > 0 ? (
        <div className="rounded-[8px] border border-red-500/25 bg-red-50/40 px-4 py-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-red-700">
            <AppIcon icon={AlertTriangle} size="xs" /> Quarantine Candidates ({result.quarantineCandidates.length})
          </p>
          <ul className="mt-1.5 space-y-0.5">
            {result.quarantineCandidates.map((f) => (
              <li key={f.storeId} className="text-micro text-red-700">Store #{f.storeId} — {f.reason}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 rounded-[8px] bg-green-100 px-4 py-2.5 text-xs font-medium text-green-700">
          <AppIcon icon={CheckCircle2} size="xs" /> No stores require quarantine.
        </div>
      )}
    </div>
  )
}
