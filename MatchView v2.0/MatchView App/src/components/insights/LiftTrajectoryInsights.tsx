import { TrendingUp } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import type { LiftTrajectoryResult } from '../../data/storeMonitoring'
import { simulateDriverDecomposition } from '../../data/storeDriverDecomposition'
import { DriverDecompositionCard } from './DriverDecompositionCard'

interface Props {
  experimentKey: string
}

export function LiftTrajectoryInsights({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['sequential-testing']?.lastResult as LiftTrajectoryResult | undefined
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run In-Flight Lift Trajectory Analysis from the module panel to see the weekly time-series here.
      </div>
    )
  }

  const maxAbsLift = Math.max(1, ...result.weeklyPoints.map((p) => Math.abs(p.liftPercent)))

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={TrendingUp} size="sm" className="text-border-muted" />
          <p className="type-overline">Weekly POS Time-Series Lift — Treated vs. Matched Control</p>
        </div>
        <div className="flex items-end gap-1" style={{ height: '100px' }}>
          {result.weeklyPoints.map((p) => {
            const heightPct = (Math.abs(p.liftPercent) / maxAbsLift) * 100
            const barHeightPx = 6 + (Math.max(heightPct, 4) / 100) * 74
            return (
              <div key={p.week} className="flex flex-1 flex-col items-center justify-end gap-1" style={{ height: '100px' }} title={`Week ${p.week}: ${p.liftPercent.toFixed(2)}%`}>
                <div className={`w-full rounded-t-sm ${p.liftPercent >= 0 ? 'bg-green-500' : 'bg-red-500'}`} style={{ height: `${barHeightPx}px` }} />
                <span className="text-[9px] text-text-secondary">W{p.week}</span>
              </div>
            )
          })}
        </div>
        <p className="mt-2 text-micro text-text-secondary">
          Latest: {result.weeklyPoints[result.weeklyPoints.length - 1]?.liftPercent.toFixed(2)}% lift vs. matched
          control — {result.rampHorizonWeeks}-week ramp horizon
        </p>
      </div>

      <DriverDecompositionCard
        title="In-Flight Sales Driver Decomposition (Preliminary)"
        decomposition={simulateDriverDecomposition(testStoreCount, 1)}
      />

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <p className="type-overline mb-1.5">Emerging Metrics Summary</p>
        <p className="mb-2 text-micro text-amber-700">Preliminary, unadjusted directional indicators — not yet a final readout.</p>
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
    </div>
  )
}
