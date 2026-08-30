import { useEffect, useRef, useState } from 'react'
import { Waves, Loader2, CheckCircle2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import { type MoneyWaterfallResult, simulateRoiSynthesis } from '../../data/storeCausalRoi'

function formatMoney(n: number): string {
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString()}`
}

export function StoreRoiSynthesisPanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField, moduleRunStatus, labModuleId } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const opportunity = values['opportunity-sizing'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500
  const initiativeCost = typeof opportunity.estimatedInitiativeCost === 'number' ? opportunity.estimatedInitiativeCost : 800000
  const grossMarginPercent = typeof opportunity.grossMargin === 'number' ? opportunity.grossMargin : 0.31

  const [result, setResult] = useState<MoneyWaterfallResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Auto-run simulation when a chat-triggered module run completes for roi-synthesis
  const prevRunStatusRef = useRef<string>(moduleRunStatus)
  useEffect(() => {
    if (
      prevRunStatusRef.current === 'running' &&
      moduleRunStatus === 'success' &&
      labModuleId === 'roi-synthesis' &&
      !isRunning
    ) {
      setIsRunning(true)
      setResult(null)
      simulateRoiSynthesis(testStoreCount, initiativeCost, grossMarginPercent)
        .then((r) => {
          setResult(r)
          updateModuleFormField('roi-synthesis' as any, 'lastResult', r)
        })
        .catch(() => setError('Auto-run failed — try running manually.'))
        .finally(() => setIsRunning(false))
    }
    prevRunStatusRef.current = moduleRunStatus
  }, [moduleRunStatus, labModuleId])

  const run = async () => {
    setError(null)
    setIsRunning(true)
    setResult(null)
    try {
      const r = await simulateRoiSynthesis(testStoreCount, initiativeCost, grossMarginPercent)
      setResult(r)
      updateModuleFormField('roi-synthesis' as any, 'lastResult', r)
    } catch {
      setError('ROI synthesis failed to run — try again.')
    } finally {
      setIsRunning(false)
    }
  }

  const waterfallRows = result ? [
    { label: 'Gross Incremental POS Revenue', value: result.grossIncrementalRevenue, isTotal: false },
    { label: '+ Cross-Category Halo Lift', value: result.crossCategoryHaloLift, isTotal: false },
    { label: '- Category Cannibalization', value: result.categoryCannibalization, isTotal: false },
    { label: '= Net Incremental Sales', value: result.netIncrementalSales, isTotal: true },
    { label: '- Cost of Goods Sold', value: result.cogs, isTotal: false },
    { label: '- Store Operational Execution Cost', value: result.operationalExecutionCost, isTotal: false },
    { label: '= Final Net Incremental Margin', value: result.finalNetIncrementalMargin, isTotal: true },
  ] : []

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <p className="type-overline mb-1">P&L Money Waterfall</p>
          <p className="text-micro text-text-secondary leading-relaxed">
            Converts raw revenue lift into verifiable net profit that reconciles directly back to
            corporate financial statements.
          </p>
        </div>

        {error && <p className="text-micro text-red-600">{error}</p>}

        {result && !isRunning && (
          <>
            <div className="overflow-hidden rounded-[8px] border border-border-muted/20">
              <table className="w-full text-left text-xs">
                <tbody>
                  {waterfallRows.map((row) => (
                    <tr key={row.label} className={`border-t border-border-muted/15 first:border-t-0 ${row.isTotal ? 'bg-surface-hover/50' : ''}`}>
                      <td className={`px-2.5 py-1.5 ${row.isTotal ? 'font-semibold text-text-primary' : 'text-text-secondary'}`}>{row.label}</td>
                      <td className={`px-2.5 py-1.5 text-right tabular-nums ${row.isTotal ? 'font-bold text-text-primary' : row.value < 0 ? 'text-red-600' : 'text-green-700'}`}>
                        {formatMoney(row.value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="rounded-[8px] border border-green-500/25 bg-green-50/5 px-3 py-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">Realized iROAS</span>
                <span className="text-sm font-bold tabular-nums text-text-primary">{result.realizedIroas.toFixed(2)}x</span>
              </div>
              {result.reconciliationConfirmed && (
                <p className="mt-1.5 flex items-center gap-1.5 text-micro text-green-700">
                  <AppIcon icon={CheckCircle2} size="xs" /> Reconciliation confirmed — total test lift + control trend = total realized chain POS sales.
                </p>
              )}
            </div>
          </>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button type="button" onClick={run} disabled={isRunning}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
          {isRunning ? (<><AppIcon icon={Loader2} size="xs" className="animate-spin" /> Building money waterfall…</>) : (<><AppIcon icon={Waves} size="xs" /> Run ROI Synthesis</>)}
        </button>
      </div>
    </div>
  )
}
