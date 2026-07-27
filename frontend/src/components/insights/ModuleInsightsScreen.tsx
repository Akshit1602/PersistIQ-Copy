import type { ModuleId } from '../../context/types'
import { useMatchView } from '../../context/MatchViewContext'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { ExposureTrendCard } from './ExposureTrendCard'
import { InsightsDashboardGrid } from './InsightsDashboardGrid'
import { MetricSheetCard } from './MetricSheetCard'
import { SegmentConversionCard } from './SegmentConversionCard'

interface ModuleInsightsScreenProps {
  moduleId: ModuleId
}

export function ModuleInsightsScreen({ moduleId }: ModuleInsightsScreenProps) {
  const { moduleRunStatus } = useMatchView()
  const mod = MODULE_BY_ID[moduleId]

  const statusCopy =
    moduleRunStatus === 'running'
      ? 'Execution in progress…'
      : moduleRunStatus === 'success'
        ? `Last run completed in ${mod.mockDuration}.`
        : `High-density analytical dashboard for ${mod.label}.`

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="type-title">{mod.label}</h2>
          <span className="rounded-lg border border-border-muted/25 bg-surface-hover px-2 py-0.5 text-xs text-text-secondary">
            {mod.phaseLabel}
          </span>
        </div>
        <p className="type-subtitle shrink-0 pt-0.5 leading-tight">
          {statusCopy}
        </p>
      </div>

      <InsightsDashboardGrid featured={<ExposureTrendCard chartId={`${moduleId}-exposure`} />}>
        <SegmentConversionCard chartId={`${moduleId}-segments`} />
        <MetricSheetCard chartId={`${moduleId}-metrics`} />
        <SegmentConversionCard chartId={`${moduleId}-funnel`} title="Funnel Drop-off" />
        <MetricSheetCard chartId={`${moduleId}-raw`} title="Execution Output" />
      </InsightsDashboardGrid>
    </div>
  )
}
