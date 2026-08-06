import { useEffect, useRef, useState } from 'react'
import { LineChart, Loader2, Info, X } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import { TimeSeriesLineChart } from '../shared/TimeSeriesLineChart'
import {
  type ForecastingResult,
  type ForecastingModel,
  FORECASTING_MODEL_OPTIONS,
  simulateForecasting,
} from '../../data/storeCausalRoi'

const selectClass =
  'focus-ring box-border w-full min-w-0 appearance-none rounded-xs border border-border-muted/25 bg-surface-base bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat px-2.5 py-1.5 pr-8 text-xs text-text-primary'
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"
const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary'

export function StoreForecastingPanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField, moduleRunStatus, labModuleId } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500
  const forecastingValues = values['forecasting'] ?? {}
  const persistedWeeksOfFlight = typeof forecastingValues.weeksOfFlight === 'number' ? forecastingValues.weeksOfFlight : 12
  const persistedHorizonWeeks = [12, 26, 52].includes(forecastingValues.horizonWeeks as number)
    ? (forecastingValues.horizonWeeks as 12 | 26 | 52)
    : 26

  const [weeksOfFlight, setWeeksOfFlightState] = useState(persistedWeeksOfFlight)
  const [horizonWeeks, setHorizonWeeksState] = useState<12 | 26 | 52>(persistedHorizonWeeks)
  const [selectedModels, setSelectedModels] = useState<ForecastingModel[]>(['arima'])
  const [infoModel, setInfoModel] = useState<ForecastingModel | null>(null)
  const [result, setResult] = useState<ForecastingResult | null>(null)
  const [comparisonResults, setComparisonResults] = useState<ForecastingResult[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fleetSliderIdx, setFleetSliderIdx] = useState(0)

  // Keep local state in sync if chat (NLP extraction) injects new values while
  // this panel is mounted — e.g. "show me only 5 week forecasting".
  useEffect(() => {
    setWeeksOfFlightState(persistedWeeksOfFlight)
    setHorizonWeeksState(persistedHorizonWeeks)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persistedWeeksOfFlight, persistedHorizonWeeks])

  // Auto-run simulation when a chat-triggered module run completes for forecasting
  const prevRunStatusRef = useRef<string>(moduleRunStatus)
  useEffect(() => {
    if (
      prevRunStatusRef.current === 'running' &&
      moduleRunStatus === 'success' &&
      labModuleId === 'forecasting' &&
      !isRunning
    ) {
      // Chat triggered a forecasting run — auto-execute the actual simulation
      const chatModel = (forecastingValues.model as ForecastingModel) || selectedModels[0] || 'arima'
      const chatWeeks = typeof forecastingValues.weeksOfFlight === 'number' ? forecastingValues.weeksOfFlight : weeksOfFlight
      const chatHorizon = [12, 26, 52].includes(forecastingValues.horizonWeeks as number)
        ? (forecastingValues.horizonWeeks as 12 | 26 | 52)
        : horizonWeeks

      // Sync local state from chat-injected values
      setWeeksOfFlightState(chatWeeks)
      setHorizonWeeksState(chatHorizon)
      if (!selectedModels.includes(chatModel)) {
        setSelectedModels((prev) => [chatModel, ...prev.filter((m) => m !== chatModel)])
      }

      // Run the simulation
      setIsRunning(true)
      setResult(null)
      setComparisonResults([])
      const modelsToRun = selectedModels.includes(chatModel) ? selectedModels : [chatModel, ...selectedModels]
      Promise.all(
        modelsToRun.map((m) => simulateForecasting(testStoreCount, chatWeeks, chatHorizon, m)),
      ).then((allResults) => {
        setResult(allResults[0])
        setComparisonResults(allResults)
        updateModuleFormField('forecasting' as any, 'lastResult', allResults[0])
        setIsRunning(false)
      }).catch(() => {
        setError('Auto-run failed — try running manually.')
        setIsRunning(false)
      })
    }
    prevRunStatusRef.current = moduleRunStatus
  }, [moduleRunStatus, labModuleId])

  const setWeeksOfFlight = (n: number) => {
    setWeeksOfFlightState(n)
    updateModuleFormField('forecasting' as any, 'weeksOfFlight', n)
  }
  const setHorizonWeeks = (n: 12 | 26 | 52) => {
    setHorizonWeeksState(n)
    updateModuleFormField('forecasting' as any, 'horizonWeeks', n)
  }

  const toggleModel = (m: ForecastingModel) => {
    setSelectedModels((prev) => {
      if (prev.includes(m)) {
        // Never allow zero models selected — always keep at least one.
        return prev.length > 1 ? prev.filter((x) => x !== m) : prev
      }
      return [...prev, m]
    })
  }

  const run = async () => {
    setError(null)
    setIsRunning(true)
    setResult(null)
    setComparisonResults([])
    try {
      const modelsToRun = selectedModels.length > 0 ? selectedModels : (['arima'] as ForecastingModel[])
      const allResults = await Promise.all(
        modelsToRun.map((m) => simulateForecasting(testStoreCount, weeksOfFlight, horizonWeeks, m)),
      )
      const primary = allResults[0]
      setResult(primary)
      setComparisonResults(allResults)
      updateModuleFormField('forecasting' as any, 'lastResult', primary)
    } catch {
      setError('Forecast failed to run — try again.')
    } finally {
      setIsRunning(false)
    }
  }



  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <label className="type-caption mb-0.5 block">Forecasting Model(s)</label>
          <p className="mb-1.5 text-micro text-text-secondary">
            Select one or more estimators to compare — the first checked model drives the main chart below.
          </p>
          <div className="flex flex-col gap-1.5 max-h-[320px] overflow-y-auto pr-1">
            {FORECASTING_MODEL_OPTIONS.map((o) => (
              <div key={o.value} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5 h-3.5 w-3.5 accent-current shrink-0"
                  checked={selectedModels.includes(o.value)}
                  onChange={() => toggleModel(o.value)}
                  id={`fcm-${o.value}`}
                />
                <label htmlFor={`fcm-${o.value}`} className="flex-1 min-w-0 cursor-pointer">
                  <span className="block text-xs font-medium text-text-primary">{o.label}</span>
                  <span className="block text-micro text-text-secondary">{o.hint}</span>
                </label>
                <button
                  type="button"
                  className="shrink-0 mt-0.5 rounded-full p-0.5 text-text-secondary hover:text-text-primary hover:bg-surface-hover/60 transition-colors"
                  onClick={() => setInfoModel(infoModel === o.value ? null : o.value)}
                  title="Model details"
                >
                  <AppIcon icon={Info} size="xs" />
                </button>
              </div>
            ))}
          </div>
          {infoModel && (
            <div className="mt-2 rounded-xs border border-blue-200/40 bg-blue-50/10 px-3 py-2.5 relative">
              <button
                type="button"
                className="absolute top-1.5 right-1.5 rounded-full p-0.5 text-text-secondary hover:text-text-primary"
                onClick={() => setInfoModel(null)}
              >
                <AppIcon icon={X} size="xs" />
              </button>
              <p className="text-xs font-semibold text-text-primary mb-1">
                {FORECASTING_MODEL_OPTIONS.find((o) => o.value === infoModel)?.label}
              </p>
              <p className="text-micro text-text-secondary leading-relaxed pr-4">
                {FORECASTING_MODEL_OPTIONS.find((o) => o.value === infoModel)?.description}
              </p>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <label className="type-caption mb-0.5 block">Weeks of Flight Observed</label>
            <input type="number" className={inputClass} value={weeksOfFlight} min={1} max={52}
              onChange={(e) => setWeeksOfFlight(Number(e.target.value) || 1)} />
          </div>
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <label className="type-caption mb-0.5 block">Future Horizon</label>
            <select className={selectClass} style={{ backgroundImage: selectChevronBg }} value={horizonWeeks}
              onChange={(e) => setHorizonWeeks(Number(e.target.value) as 12 | 26 | 52)}>
              <option value={12}>12 Weeks</option>
              <option value={26}>26 Weeks</option>
              <option value={52}>52 Weeks</option>
            </select>
          </div>
        </div>

        {error && <p className="text-micro text-red-600">{error}</p>}

        {result && !isRunning && (
          <>
            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <p className="type-overline mb-2">Weekly Time Series — Realized Sales vs. Counterfactual (Predicted Baseline)</p>
              <TimeSeriesLineChart
                seriesA={result.weeklyPoints.map((p) => ({ x: p.week, y: p.predictedBaseline }))}
                seriesALabel="Counterfactual (Predicted Baseline)"
                seriesB={result.weeklyPoints.map((p) => ({ x: p.week, y: p.realizedSales }))}
                seriesBLabel="Realized Sales"
                formatY={(v) => `$${Math.round(v / 1000)}k`}
                formatX={(v) => `W${v}`}
              />
              <div className="mt-2 flex items-center gap-4 text-micro text-text-secondary">
                <span className="flex items-center gap-1"><span className="h-2 w-0.5 border-t-2 border-dashed border-slate-400" /> Counterfactual (Predicted Baseline)</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-green-600" /> Realized Sales</span>
              </div>
              <p className="mt-2 text-micro text-text-secondary">
                Latest: {result.weeklyPoints[result.weeklyPoints.length-1]?.liftPercent}% lift · Δ ${result.weeklyPoints[result.weeklyPoints.length-1]?.incrementalDeltaDollars.toLocaleString()} vs. predicted baseline (95% band: {result.weeklyPoints[result.weeklyPoints.length-1]?.ciLoPercent}% to {result.weeklyPoints[result.weeklyPoints.length-1]?.ciHiPercent}%)
              </p>
            </div>

            {comparisonResults.length > 1 && (
              <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
                <p className="type-overline mb-2">Model Comparison</p>
                <div className="overflow-hidden rounded-xs border border-border-muted/20">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-surface-hover/60">
                      <tr>
                        <th className="px-2.5 py-1.5 font-medium text-text-secondary">Model</th>
                        <th className="px-2.5 py-1.5 font-medium text-text-secondary">Projected Future Lift</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparisonResults.map((r) => (
                        <tr key={r.model} className="border-t border-border-muted/15">
                          <td className="px-2.5 py-1.5 text-text-primary">
                            {FORECASTING_MODEL_OPTIONS.find((o) => o.value === r.model)?.label ?? r.model}
                          </td>
                          <td className="px-2.5 py-1.5 tabular-nums font-medium text-text-primary">
                            {r.projectedFutureLiftPercent >= 0 ? '+' : ''}{r.projectedFutureLiftPercent.toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <p className="type-overline mb-1">Post-Flight Horizon Prediction</p>
              <p className="text-xs text-text-secondary">
                Projected steady-state lift at <strong>{horizonWeeks} weeks</strong>: <strong className="text-text-primary">{result.projectedFutureLiftPercent >= 0 ? '+' : ''}{result.projectedFutureLiftPercent}%</strong> (decay-adjusted from observed flight ramp)
              </p>
            </div>

            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <p className="type-overline mb-1.5">Full-Fleet Scale Simulator</p>
              <input type="range" min={0} max={result.fullFleetSimulation.length - 1} step={1} value={fleetSliderIdx}
                onChange={(e) => setFleetSliderIdx(Number(e.target.value))} className="w-full" />
              <div className="mt-1.5 flex items-center justify-between text-xs">
                <span className="text-text-secondary">{result.fullFleetSimulation[fleetSliderIdx]?.storeCount.toLocaleString()} stores</span>
                <span className="font-semibold text-text-primary tabular-nums">
                  ${result.fullFleetSimulation[fleetSliderIdx]?.projectedAnnualLiftDollars.toLocaleString()} / yr
                </span>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button type="button" onClick={run} disabled={isRunning}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
          {isRunning ? (<><AppIcon icon={Loader2} size="xs" className="animate-spin" /> Building forecast…</>) : (<><AppIcon icon={LineChart} size="xs" /> Run Forecast & Counterfactual</>)}
        </button>
      </div>
    </div>
  )
}
