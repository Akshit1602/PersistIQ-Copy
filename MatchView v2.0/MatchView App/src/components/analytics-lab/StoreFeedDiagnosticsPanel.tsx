import { useState } from 'react'
import { Wifi, Loader2, CheckCircle2, AlertTriangle, PackageX } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import {
  type StoreFeedDiagnosticsResult,
  type StoreFeedChecksToggle,
  STORE_FEED_CHECKS_DEFAULTS,
  simulateStoreFeedDiagnostics,
} from '../../data/storeMonitoring'

export function StoreFeedDiagnosticsPanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500

  const [checks, setChecks] = useState<StoreFeedChecksToggle>(STORE_FEED_CHECKS_DEFAULTS)
  const [result, setResult] = useState<StoreFeedDiagnosticsResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const noneSelected = !checks.runPosIngestion && !checks.runStockoutFilter && !checks.runExecutionRate

  const run = async () => {
    if (noneSelected) return
    setError(null)
    setIsRunning(true)
    setResult(null)
    try {
      const r = await simulateStoreFeedDiagnostics(testStoreCount, checks)
      setResult(r)
      updateModuleFormField('experiment-analysis' as any, 'lastResult', r)
    } catch {
      setError('Diagnostics failed to run — try again.')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <p className="text-micro text-text-secondary">Select which checks to run:</p>

        <label className="flex cursor-pointer items-start gap-2 rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3 hover:bg-surface-hover">
          <input
            type="checkbox"
            className="mt-0.5 h-3.5 w-3.5 accent-current"
            checked={checks.runPosIngestion}
            onChange={(e) => setChecks((c) => ({ ...c, runPosIngestion: e.target.checked }))}
          />
          <span className="min-w-0">
            <span className="type-overline block">POS Ingestion Status</span>
            <span className="mt-0.5 block text-micro text-text-secondary leading-relaxed">
              Checks that 100% of Test and Control store POS feeds are reporting without data gaps.
            </span>
          </span>
        </label>

        <label className="flex cursor-pointer items-start gap-2 rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3 hover:bg-surface-hover">
          <input
            type="checkbox"
            className="mt-0.5 h-3.5 w-3.5 accent-current"
            checked={checks.runStockoutFilter}
            onChange={(e) => setChecks((c) => ({ ...c, runStockoutFilter: e.target.checked }))}
          />
          <span className="min-w-0">
            <span className="type-overline block">Stockout Velocity Filter</span>
            <span className="mt-0.5 block text-micro text-text-secondary leading-relaxed">
              Flags stores where primary test SKUs are out of stock for &gt;24 hours to prevent false
              negative lift calculations.
            </span>
          </span>
        </label>

        <label className="flex cursor-pointer items-start gap-2 rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3 hover:bg-surface-hover">
          <input
            type="checkbox"
            className="mt-0.5 h-3.5 w-3.5 accent-current"
            checked={checks.runExecutionRate}
            onChange={(e) => setChecks((c) => ({ ...c, runExecutionRate: e.target.checked }))}
          />
          <span className="min-w-0">
            <span className="type-overline block">Operational Execution Rate</span>
            <span className="mt-0.5 block text-micro text-text-secondary leading-relaxed">
              % of stores meeting intervention criteria. Stores falling below execution thresholds can be
              quarantined.
            </span>
          </span>
        </label>

        {error && <p className="text-micro text-red-600">{error}</p>}
        {noneSelected && <p className="text-micro text-amber-700">Select at least one check to run.</p>}

        {result && !isRunning && (
          <div className="flex flex-col gap-2.5">
            {result.posIngestionPercent !== null && (
              <div className="rounded-[8px] border border-border-muted/15 bg-surface-hover/40 px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-secondary">POS Ingestion</span>
                  <span className={`text-sm font-bold tabular-nums ${result.posIngestionPercent >= 99 ? 'text-green-600' : 'text-amber-700'}`}>
                    {result.posIngestionPercent.toFixed(1)}%
                  </span>
                </div>
                {result.storesWithDataGaps > 0 && (
                  <p className="mt-0.5 text-micro text-amber-700">{result.storesWithDataGaps} store(s) with data gaps</p>
                )}
              </div>
            )}

            {result.operationalExecutionRatePercent !== null && (
              <div className="rounded-[8px] border border-border-muted/15 bg-surface-hover/40 px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-secondary">Operational Execution Rate</span>
                  <span className={`text-sm font-bold tabular-nums ${result.operationalExecutionRatePercent >= 92 ? 'text-green-600' : 'text-amber-700'}`}>
                    {result.operationalExecutionRatePercent.toFixed(1)}%
                  </span>
                </div>
              </div>
            )}

            {result.stockoutFlags !== null && result.stockoutFlags.length > 0 && (
              <div className="rounded-[8px] border border-amber-500/25 bg-amber-50/40 px-3 py-2.5">
                <p className="flex items-center gap-1.5 text-xs font-medium text-amber-800">
                  <AppIcon icon={PackageX} size="xs" /> Stockout Flags ({result.stockoutFlags.length})
                </p>
                <ul className="mt-1 space-y-0.5">
                  {result.stockoutFlags.map((f) => (
                    <li key={f.storeId} className="text-micro text-amber-800">Store #{f.storeId} — {f.reason}</li>
                  ))}
                </ul>
              </div>
            )}

            {result.quarantineCandidates !== null && (
              result.quarantineCandidates.length > 0 ? (
                <div className="rounded-[8px] border border-red-500/25 bg-red-50/40 px-3 py-2.5">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-red-700">
                    <AppIcon icon={AlertTriangle} size="xs" /> Quarantine Candidates ({result.quarantineCandidates.length})
                  </p>
                  <ul className="mt-1 space-y-0.5">
                    {result.quarantineCandidates.map((f) => (
                      <li key={f.storeId} className="text-micro text-red-700">Store #{f.storeId} — {f.reason}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 rounded-[8px] bg-green-100 px-3 py-2 text-xs font-medium text-green-700">
                  <AppIcon icon={CheckCircle2} size="xs" /> No stores require quarantine.
                </div>
              )
            )}
          </div>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button
          type="button"
          onClick={run}
          disabled={isRunning || noneSelected}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isRunning ? (
            <>
              <AppIcon icon={Loader2} size="xs" className="animate-spin" />
              Checking store feeds…
            </>
          ) : (
            <>
              <AppIcon icon={Wifi} size="xs" />
              Run Feed & Execution Check
            </>
          )}
        </button>
      </div>
    </div>
  )
}
