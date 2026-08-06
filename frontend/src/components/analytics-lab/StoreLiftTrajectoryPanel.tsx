import { useState } from 'react'
import { TrendingUp, Loader2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import { type LiftTrajectoryResult, simulateLiftTrajectory } from '../../data/storeMonitoring'
import { simulateDriverDecomposition } from '../../data/storeDriverDecomposition'
import { DriverDecompositionCard } from '../insights/DriverDecompositionCard'

const selectClass =
  'focus-ring box-border w-full min-w-0 appearance-none rounded-xs border border-border-muted/25 bg-surface-base bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat px-2.5 py-1.5 pr-8 text-xs text-text-primary'
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"
const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary'

export function StoreLiftTrajectoryPanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500

  const [weeksElapsed, setWeeksElapsed] = useState(6)
  const [rampHorizonWeeks, setRampHorizonWeeks] = useState<4 | 13>(13)
  const [result, setResult] = useState<LiftTrajectoryResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setError(null)
    setIsRunning(true)
    setResult(null)
    try {
      const r = await simulateLiftTrajectory(testStoreCount, weeksElapsed, rampHorizonWeeks)
      setResult(r)
      updateModuleFormField('sequential-testing' as any, 'lastResult', r)
    } catch {
      setError('Trajectory analysis failed to run — try again.')
    } finally {
      setIsRunning(false)
    }
  }

  const maxAbsLift = result ? Math.max(1, ...result.weeklyPoints.map((p) => Math.abs(p.liftPercent))) : 1

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <label className="type-caption mb-0.5 block">Weeks Elapsed</label>
            <input
              type="number"
              className={inputClass}
              value={weeksElapsed}
              min={1}
              max={52}
              onChange={(e) => setWeeksElapsed(Number(e.target.value) || 1)}
            />
          </div>
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <label className="type-caption mb-0.5 block">Visit Lag Ramp Horizon</label>
            <select
              className={selectClass}
              style={{ backgroundImage: selectChevronBg }}
              value={rampHorizonWeeks}
              onChange={(e) => setRampHorizonWeeks(Number(e.target.value) as 4 | 13)}
            >
              <option value={4}>4-Week Immediate</option>
              <option value={13}>13-Week Sustained</option>
            </select>
          </div>
        </div>

        {error && <p className="text-micro text-red-600">{error}</p>}

        {result && !isRunning && (
          <>
            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <p className="type-overline mb-2">Weekly Time-Series Lift</p>
              <div className="flex items-end gap-1" style={{ height: '96px' }}>
                {result.weeklyPoints.map((p) => {
                  const heightPct = (Math.abs(p.liftPercent) / maxAbsLift) * 100
                  const barHeightPx = 6 + (Math.max(heightPct, 4) / 100) * 64
                  return (
                    <div key={p.week} className="flex flex-1 flex-col items-center justify-end gap-0.5" style={{ height: '96px' }} title={`Week ${p.week}: ${p.liftPercent.toFixed(2)}%`}>
                      <div
                        className={`w-full rounded-t-sm ${p.liftPercent >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                        style={{ height: `${barHeightPx}px` }}
                      />
                      <span className="text-[9px] text-text-secondary">W{p.week}</span>
                    </div>
                  )
                })}
              </div>
              <p className="mt-2 text-micro text-text-secondary">
                Latest: {result.weeklyPoints[result.weeklyPoints.length - 1]?.liftPercent.toFixed(2)}% lift vs.
                matched control — {result.rampHorizonWeeks}-week ramp horizon
              </p>
            </div>

            <DriverDecompositionCard
              title="In-Flight Sales Driver Decomposition (Preliminary)"
              decomposition={simulateDriverDecomposition(testStoreCount, 1)}
            />

            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <p className="type-overline mb-2">Emerging Metrics Summary</p>
              <p className="mb-1.5 text-micro text-amber-700">Preliminary, unadjusted directional indicators — not yet a final readout.</p>
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xs bg-surface-hover/40 px-2.5 py-2">
                  <p className="text-micro text-text-secondary">Primary KPI (directional)</p>
                  <p className="text-sm font-semibold text-text-primary tabular-nums">
                    {result.emergingMetrics.primaryKpiDirectionalLiftPercent >= 0 ? '+' : ''}
                    {result.emergingMetrics.primaryKpiDirectionalLiftPercent.toFixed(2)}%
                  </p>
                </div>
                <div className="rounded-xs bg-surface-hover/40 px-2.5 py-2">
                  <p className="text-micro text-text-secondary">Secondary KPI (directional)</p>
                  <p className="text-sm font-semibold text-text-primary tabular-nums">
                    {result.emergingMetrics.secondaryKpiDirectionalLiftPercent >= 0 ? '+' : ''}
                    {result.emergingMetrics.secondaryKpiDirectionalLiftPercent.toFixed(2)}%
                  </p>
                </div>
                <div className="col-span-2 rounded-xs bg-surface-hover/40 px-2.5 py-2">
                  <p className="text-micro text-text-secondary">Operational Guardrails</p>
                  <p className={`text-xs font-semibold ${result.emergingMetrics.guardrailStatus === 'watch' ? 'text-amber-700' : 'text-green-700'}`}>
                    {result.emergingMetrics.guardrailStatus === 'watch' ? 'Watch' : 'Within Normal Range'}
                  </p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button
          type="button"
          onClick={run}
          disabled={isRunning}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isRunning ? (
            <>
              <AppIcon icon={Loader2} size="xs" className="animate-spin" />
              Building trajectory…
            </>
          ) : (
            <>
              <AppIcon icon={TrendingUp} size="xs" />
              Run Lift Trajectory Analysis
            </>
          )}
        </button>
      </div>
    </div>
  )
}
