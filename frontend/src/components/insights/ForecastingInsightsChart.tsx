import { TrendingUp } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { TimeSeriesLineChart } from '../shared/TimeSeriesLineChart'
import type { ForecastingResult } from '../../data/storeCausalRoi'

interface Props {
  experimentKey: string
}

export function ForecastingInsightsChart({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['forecasting']?.lastResult as ForecastingResult | undefined

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run the Forecasting & Counterfactual Predictor from the module panel to see the weekly forecast
        chart here.
      </div>
    )
  }

  const displayRows = result.weeklyPoints.slice(0, 16)

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={TrendingUp} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">
            Weekly Time Series — Realized Sales vs. Counterfactual ({result.horizonWeeks}-week horizon, {result.model.toUpperCase()})
          </p>
        </div>
        {(() => {
          const weekAt = (i: number) => displayRows[i]?.week ?? i
          return (
            <TimeSeriesLineChart
              seriesA={displayRows.map((r, i) => ({ x: weekAt(i), y: r.predictedBaseline }))}
              seriesALabel="Counterfactual (Predicted Baseline)"
              seriesB={displayRows.map((r, i) => ({ x: weekAt(i), y: r.realizedSales }))}
              seriesBLabel="Realized Sales"
              formatY={(v) => `$${Math.round(v / 1000)}k`}
              formatX={(v) => `W${v}`}
            />
          )
        })()}
        <div className="mt-2 flex items-center gap-4 text-micro text-text-secondary">
          <span className="flex items-center gap-1"><span className="h-2 w-0.5 border-t-2 border-dashed border-slate-400" /> Counterfactual (Predicted Baseline)</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-green-600" /> Realized Sales</span>
        </div>
      </div>

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3 overflow-x-auto">
        <p className="type-overline mb-2">Weekly Incremental Delta</p>
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-text-secondary">
              <th className="pr-3 py-1">Week</th>
              <th className="pr-3 py-1">Delta ($)</th>
              <th className="pr-3 py-1">Lift %</th>
              <th className="py-1">95% CI (lift %)</th>
            </tr>
          </thead>
          <tbody>
            {displayRows.slice(0, 8).map((row) => (
              <tr key={row.week} className="border-t border-border-muted/10">
                <td className="pr-3 py-1">W{row.week}</td>
                <td className={`pr-3 py-1 tabular-nums font-medium ${row.incrementalDeltaDollars >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {row.incrementalDeltaDollars >= 0 ? '+' : ''}{row.incrementalDeltaDollars.toLocaleString()}
                </td>
                <td className="pr-3 py-1 tabular-nums">{row.liftPercent.toFixed(2)}%</td>
                <td className="py-1 tabular-nums text-text-secondary">[{row.ciLoPercent.toFixed(2)}%, {row.ciHiPercent.toFixed(2)}%]</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <p className="type-overline mb-2">Full-Fleet Scale Simulation</p>
        <p className="mb-2 text-micro text-text-secondary">
          Projected {result.projectedFutureLiftPercent.toFixed(2)}% steady-state lift, applied at scale:
        </p>
        <div className="grid grid-cols-3 gap-2">
          {result.fullFleetSimulation.map((pt) => (
            <div key={pt.storeCount} className="rounded-xs bg-surface-hover/40 px-2.5 py-2">
              <p className="text-micro text-text-secondary">{pt.storeCount.toLocaleString()} stores</p>
              <p className="text-xs font-semibold text-text-primary tabular-nums">
                ${pt.projectedAnnualLiftDollars.toLocaleString()}/yr
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
