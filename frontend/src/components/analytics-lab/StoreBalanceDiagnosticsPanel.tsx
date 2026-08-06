import { useState } from 'react'
import { Scale, Play, Loader2, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import { InfoTooltip } from '../shared/InfoTooltip'
import {
  type LookbackWindow,
  type StoreBalanceDiagnosticsState,
  LOOKBACK_WINDOW_OPTIONS,
  STORE_BALANCE_DIAGNOSTICS_DEFAULTS,
  simulateBalanceDiagnostics,
} from '../../data/storeBalanceDiagnostics'

const selectClass =
  'focus-ring box-border w-full min-w-0 appearance-none rounded-xs border border-border-muted/25 bg-surface-base bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat px-2.5 py-1.5 pr-8 text-xs text-text-primary'
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"

export function StoreBalanceDiagnosticsPanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField, markWorkflowStepComplete } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()

  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const panelMatching = values['store-panel-matching'] ?? {}

  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500
  const matchingAlgorithmLabel =
    typeof panelMatching.algorithm === 'string' && panelMatching.algorithm === 'dtw_only'
      ? 'DTW'
      : typeof panelMatching.algorithm === 'string' && panelMatching.algorithm === 'standardized_euclidean'
        ? 'Standardized Euclidean'
        : 'D_composite'
  const driveTimeRadius = typeof rollout.driveTimeExclusionMiles === 'number' ? rollout.driveTimeExclusionMiles : 15

  const [state, setState] = useState<StoreBalanceDiagnosticsState>(STORE_BALANCE_DIAGNOSTICS_DEFAULTS)
  const [error, setError] = useState<string | null>(null)

  const patch = (partial: Partial<StoreBalanceDiagnosticsState>) => setState((s) => ({ ...s, ...partial }))
  const patchTests = (partial: Partial<StoreBalanceDiagnosticsState['tests']>) =>
    setState((s) => ({ ...s, tests: { ...s.tests, ...partial } }))

  const runDiagnostics = async () => {
    setError(null)
    patch({ isRunning: true, runResult: null })
    try {
      const result = await simulateBalanceDiagnostics(state, testStoreCount)
      patch({ isRunning: false, runResult: result })
      updateModuleFormField('balance-diagnostics' as any, 'lastResult', result)
      markWorkflowStepComplete(selectedExperiment, 'balance-diagnostics')
    } catch {
      setError('Balance diagnostics failed to run — try again.')
      patch({ isRunning: false })
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        {/* Pre-flight summary */}
        <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
          <div className="flex items-center gap-2">
            <AppIcon icon={Scale} size="sm" className="text-border-muted" />
            <p className="text-sm font-semibold text-text-primary">Pre-Flight Store Panel Audit</p>
            <span className="ml-auto rounded-xs bg-blue-100 px-1.5 py-0.5 text-micro font-semibold text-blue-700">
              READY TO EXECUTE
            </span>
          </div>
          <div className="mt-2 overflow-hidden rounded-xs border border-border-muted/20">
            <table className="w-full text-left text-xs">
              <tbody>
                <tr className="border-t border-border-muted/15 first:border-t-0">
                  <td className="px-2.5 py-1.5 text-text-secondary">Target Test Cohort</td>
                  <td className="px-2.5 py-1.5 font-medium text-text-primary tabular-nums">{testStoreCount.toLocaleString()} Stores (from Store Matching)</td>
                </tr>
                <tr className="border-t border-border-muted/15">
                  <td className="px-2.5 py-1.5 text-text-secondary">Matched Control Panel</td>
                  <td className="px-2.5 py-1.5 font-medium text-text-primary tabular-nums">{testStoreCount.toLocaleString()} Twin Stores ({matchingAlgorithmLabel})</td>
                </tr>
                <tr className="border-t border-border-muted/15">
                  <td className="px-2.5 py-1.5 text-text-secondary">Historical POS Lookback</td>
                  <td className="px-2.5 py-1.5 font-medium text-text-primary">{state.lookbackWeeks} Weeks</td>
                </tr>
                <tr className="border-t border-border-muted/15">
                  <td className="px-2.5 py-1.5 text-text-secondary">Spatial Buffer Masking</td>
                  <td className="px-2.5 py-1.5 font-medium text-text-primary">Active ({driveTimeRadius}-Mile Trade-Area Radius)</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Section 1: Pre-Period Historical Baseline Window */}
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <label className="type-overline mb-0.5 block">Historical Baseline Lookback Window</label>
          <p className="mb-1.5 text-micro text-text-secondary">
            Sets the historical window used to check pre-trend parallelism and calculate baseline sales variance.
          </p>
          <select
            className={selectClass}
            style={{ backgroundImage: selectChevronBg }}
            value={state.lookbackWeeks}
            onChange={(e) => patch({ lookbackWeeks: Number(e.target.value) as LookbackWindow })}
          >
            {LOOKBACK_WINDOW_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* Section 2: Covariate Balance Thresholds */}
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <label className="type-overline mb-0.5 block">Max Standardized Mean Difference (|SMD|)</label>
          <p className="mb-1.5 text-micro text-text-secondary">
            Industry standard threshold. Attributes with |SMD| &lt; {state.maxSmdThreshold.toFixed(2)} are
            considered statistically well-balanced.
          </p>
          <input
            type="range"
            min={0.05}
            max={0.2}
            step={0.01}
            value={state.maxSmdThreshold}
            onChange={(e) => patch({ maxSmdThreshold: Number(e.target.value) })}
            className="w-full"
          />
          <p className="mt-1 text-xs tabular-nums text-text-primary">{state.maxSmdThreshold.toFixed(2)}</p>
        </div>

        {/* Section 3: Diagnostic Tests to Execute */}
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <p className="type-overline mb-1.5">Diagnostic Tests to Execute</p>
          <div className="flex flex-col gap-2">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-current"
                checked={state.tests.runParallelPreTrends}
                onChange={(e) => patchTests({ runParallelPreTrends: e.target.checked })}
              />
              <span className="flex items-center gap-1.5 text-xs text-text-primary">
                Run Parallel Pre-Trends Test
                <InfoTooltip text="Compares 52-week sales curves using Root Mean Squared Prediction Error (RMSPE)." />
              </span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-current"
                checked={state.tests.runCovariateBalance}
                onChange={(e) => patchTests({ runCovariateBalance: e.target.checked })}
              />
              <span className="flex items-center gap-1.5 text-xs text-text-primary">
                Run Covariate Balance Check
                <InfoTooltip text="Checks balance across store size, volume decile, demographics, and pre-G.O.L.D. tier." />
              </span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-current"
                checked={state.tests.runPlaceboInTime}
                onChange={(e) => patchTests({ runPlaceboInTime: e.target.checked })}
              />
              <span className="flex items-center gap-1.5 text-xs text-text-primary">
                Execute Placebo-in-Time (A/A) Sanity Test
                <InfoTooltip text="Simulates a mock test flight on historical unexposed data to confirm a null result." />
              </span>
            </label>
          </div>
        </div>

        {error && <p className="text-micro text-red-600">{error}</p>}

        {/* Results — Pre-Flight Audit Table */}
        {state.runResult && !state.isRunning && (
          <div
            className={`rounded-[8px] border px-3 py-3 ${
              state.runResult.overallPassed ? 'border-green-500/30 bg-green-50/5' : 'border-red-500/30 bg-red-50/5'
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              <AppIcon icon={state.runResult.overallPassed ? CheckCircle2 : AlertTriangle} size="sm" className={state.runResult.overallPassed ? 'text-green-600' : 'text-red-600'} />
              <p className="text-sm font-semibold text-text-primary">
                Pre-Flight Audit Table {state.runResult.overallPassed ? 'Complete \u2705' : 'Complete — Review Needed \u26A0\uFE0F'}
              </p>
            </div>
            <div className="overflow-hidden rounded-xs border border-border-muted/20">
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-hover/60">
                  <tr>
                    <th className="px-2.5 py-1.5 font-medium text-text-secondary">Diagnostic Test</th>
                    <th className="px-2.5 py-1.5 font-medium text-text-secondary">Score</th>
                    <th className="px-2.5 py-1.5 font-medium text-text-secondary">Threshold</th>
                    <th className="px-2.5 py-1.5 font-medium text-text-secondary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-border-muted/15">
                    <td className="px-2.5 py-1.5 text-text-primary">Target Test vs. Matched Control</td>
                    <td className="px-2.5 py-1.5 tabular-nums" colSpan={2}>
                      {testStoreCount.toLocaleString()} vs. {testStoreCount.toLocaleString()} stores
                    </td>
                    <td className="px-2.5 py-1.5">
                      <span className="flex items-center gap-1 text-green-700">
                        <AppIcon icon={ShieldCheck} size="xs" /> Matched
                      </span>
                    </td>
                  </tr>
                  {state.runResult.covariateBalance && (
                    <tr className="border-t border-border-muted/15">
                      <td className="px-2.5 py-1.5 text-text-primary">Max |SMD| Score (across covariates, incl. G.O.L.D. Tier)</td>
                      <td className="px-2.5 py-1.5 tabular-nums">{state.runResult.covariateBalance.maxSmd.toFixed(3)}</td>
                      <td className="px-2.5 py-1.5 text-text-secondary">&lt; 0.10</td>
                      <td className="px-2.5 py-1.5">
                        <span className={`flex items-center gap-1 ${state.runResult.covariateBalance.allBalanced ? 'text-green-700' : 'text-red-700'}`}>
                          <AppIcon icon={state.runResult.covariateBalance.allBalanced ? ShieldCheck : AlertTriangle} size="xs" />
                          {state.runResult.covariateBalance.allBalanced ? 'PASS' : 'REVIEW'}
                        </span>
                      </td>
                    </tr>
                  )}
                  {state.runResult.rmspe && (
                    <tr className="border-t border-border-muted/15">
                      <td className="px-2.5 py-1.5 text-text-primary">Pre-Trend Parallelism (RMSPE)</td>
                      <td className="px-2.5 py-1.5 tabular-nums">{state.runResult.rmspe.rmspe.toFixed(3)}</td>
                      <td className="px-2.5 py-1.5 text-text-secondary">&lt; 0.05</td>
                      <td className="px-2.5 py-1.5">
                        <span className={`flex items-center gap-1 ${state.runResult.rmspe.passed ? 'text-green-700' : 'text-red-700'}`}>
                          <AppIcon icon={state.runResult.rmspe.passed ? ShieldCheck : AlertTriangle} size="xs" />
                          {state.runResult.rmspe.passed ? 'PASS' : 'REVIEW'}
                        </span>
                      </td>
                    </tr>
                  )}
                  {state.runResult.placeboInTime && (
                    <tr className="border-t border-border-muted/15">
                      <td className="px-2.5 py-1.5 text-text-primary">Placebo-in-Time (A/A) False-Positive Rate</td>
                      <td className="px-2.5 py-1.5 tabular-nums">{state.runResult.placeboInTime.falsePositiveRatePercent.toFixed(1)}%</td>
                      <td className="px-2.5 py-1.5 text-text-secondary">&lt; 7%</td>
                      <td className="px-2.5 py-1.5">
                        <span className={`flex items-center gap-1 ${state.runResult.placeboInTime.passed ? 'text-green-700' : 'text-red-700'}`}>
                          <AppIcon icon={state.runResult.placeboInTime.passed ? ShieldCheck : AlertTriangle} size="xs" />
                          {state.runResult.placeboInTime.passed ? 'PASS' : 'REVIEW'}
                        </span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button
          type="button"
          onClick={runDiagnostics}
          disabled={state.isRunning}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {state.isRunning ? (
            <>
              <AppIcon icon={Loader2} size="xs" className="animate-spin" />
              Running Balance Diagnostics…
            </>
          ) : (
            <>
              <AppIcon icon={Play} size="xs" />
              Run Balance Diagnostics
            </>
          )}
        </button>
      </div>
    </div>
  )
}
