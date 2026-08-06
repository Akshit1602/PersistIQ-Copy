import { Store, ArrowRight } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'

/**
 * The default Insights dashboard (ExposureTrendCard, SegmentConversionCard,
 * MetricSheetCard + MOCK_CHARTS) is hardcoded digital content — impressions,
 * Mobile/Desktop/Returning segments, web CVR. None of it applies to a store
 * experiment. This is the store-channel replacement: a clean summary of what
 * is actually known about the experiment, pointing to the real per-module
 * results (Balance Diagnostics, Store Feed Diagnostics, Lift Trajectory)
 * that live in Analytics Lab rather than duplicating fake charts here.
 */
export function StoreInsightsDashboard() {
  const { selectedExperiment, moduleFormValuesByExperiment, setTab } = useMatchView()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const panelMatching = values['store-panel-matching'] ?? {}

  const targetStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : null
  const algorithm = typeof panelMatching.algorithm === 'string' ? panelMatching.algorithm : null

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-2xl">
        <div className="flex items-center gap-2 mb-1">
          <AppIcon icon={Store} size="md" className="text-border-muted" />
          <h2 className="text-sm font-semibold text-text-primary">Store Experiment Insights</h2>
        </div>
        <p className="mb-4 text-xs text-text-secondary">
          {selectedExperiment || 'This experiment'} — physical retail store cohort
        </p>

        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-4">
          <p className="type-overline mb-2">What We Know So Far</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xs bg-surface-hover/40 px-3 py-2.5">
              <p className="text-micro text-text-secondary">Target Store Count</p>
              <p className="text-sm font-semibold text-text-primary tabular-nums">
                {targetStoreCount !== null ? targetStoreCount.toLocaleString() : 'Not yet configured'}
              </p>
            </div>
            <div className="rounded-xs bg-surface-hover/40 px-3 py-2.5">
              <p className="text-micro text-text-secondary">Matching Algorithm</p>
              <p className="text-sm font-semibold text-text-primary">
                {algorithm ? algorithm.replace(/_/g, ' ') : 'Not yet run'}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-4 py-4">
          <p className="text-xs text-text-secondary leading-relaxed">
            Detailed results — Balance Diagnostics, Store Feed & Execution Diagnostics, Peeking Protection,
            and In-Flight Lift Trajectory — live in their own modules in Analytics Lab, where each run
            produces its own pass/fail evidence rather than a generic chart.
          </p>
          <button
            type="button"
            onClick={() => setTab('chat')}
            className="focus-ring mt-3 flex items-center gap-1.5 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90"
          >
            Open Analytics Lab
            <AppIcon icon={ArrowRight} size="xs" />
          </button>
        </div>
      </div>
    </div>
  )
}
