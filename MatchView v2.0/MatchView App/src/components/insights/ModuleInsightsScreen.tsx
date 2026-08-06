import type { ModuleId } from '../../context/types'
import { Store } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'
import { ExposureTrendCard } from './ExposureTrendCard'
import { InsightsDashboardGrid } from './InsightsDashboardGrid'
import { MetricSheetCard } from './MetricSheetCard'
import { SegmentConversionCard } from './SegmentConversionCard'
import { CausalInferenceInsightsChart } from './CausalInferenceInsightsChart'
import { ForecastingInsightsChart } from './ForecastingInsightsChart'
import { RoiSynthesisWaterfallChart } from './RoiSynthesisWaterfallChart'
import { SimpsonsParadoxInsightsChart } from './SimpsonsParadoxInsightsChart'
import { LearningsRepositoryInsights } from './LearningsRepositoryInsights'
import { FoundationDiscoveryInsights } from './FoundationDiscoveryInsights'
import { BalanceDiagnosticsInsights } from './BalanceDiagnosticsInsights'
import { StoreFeedInsights } from './StoreFeedInsights'
import { PeekingProtectionInsights } from './PeekingProtectionInsights'
import { LiftTrajectoryInsights } from './LiftTrajectoryInsights'
import { StoreMatchingInsights } from './StoreMatchingInsights'
import type { FoundationModuleKey } from '../../data/storeFoundationDiscovery'

interface ModuleInsightsScreenProps {
  moduleId: ModuleId
}

export function ModuleInsightsScreen({ moduleId }: ModuleInsightsScreenProps) {
  const { moduleRunStatus, selectedExperiment, experimentProjectIds, projects } = useMatchView()
  const mod = MODULE_BY_ID[moduleId]
  const channel = projects.find((p) => p.id === experimentProjectIds[selectedExperiment])?.channel ?? 'digital'
  const STORE_LABEL_OVERRIDES: Record<string, string> = {
    'audience-selection': 'Store Matching & Panel Selection',
    'experiment-analysis': 'Store Feed & Execution Diagnostics',
    'health-monitor': 'Peeking Protection & Futility',
    'sequential-testing': 'In-Flight Lift Trajectory',
    'causal-did': 'Causal Inference Engine',
    'forecasting': 'Forecasting & Counterfactual Predictor',
    'roi-synthesis': 'ROI Synthesis (P&L Money Waterfall)',
    'simpsons-paradox': "Simpson's Paradox & Heterogeneity Checker",
    'learnings-repository': 'Learnings & Meta-Analysis Repository',
  }
  const displayLabel = channel === 'store' ? (STORE_LABEL_OVERRIDES[moduleId] ?? mod.label) : mod.label

  const statusCopy =
    moduleRunStatus === 'running'
      ? 'Execution in progress…'
      : moduleRunStatus === 'success'
        ? `Last run completed in ${mod.mockDuration}.`
        : `High-density analytical dashboard for ${mod.label}.`

  const CAUSAL_ROI_MODULE_IDS = ['causal-did', 'forecasting', 'roi-synthesis', 'simpsons-paradox', 'learnings-repository']
  const FOUNDATION_MODULE_IDS = ['data-validation', 'dimension-setup', 'distribution-shift', 'pipeline-health', 'schema-discovery', 'watchtower']
  const PRE_PLANNING_MONITORING_MODULE_IDS = ['balance-diagnostics', 'experiment-analysis', 'health-monitor', 'sequential-testing', 'audience-selection']

  if (channel === 'store' && PRE_PLANNING_MONITORING_MODULE_IDS.includes(moduleId)) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="type-title">{displayLabel}</h2>
            <span className="rounded-lg border border-border-muted/25 bg-surface-hover px-2 py-0.5 text-xs text-text-secondary">
              {mod.phaseLabel}
            </span>
          </div>
        </div>
        {moduleId === 'balance-diagnostics' && <BalanceDiagnosticsInsights experimentKey={selectedExperiment} />}
        {moduleId === 'experiment-analysis' && <StoreFeedInsights experimentKey={selectedExperiment} />}
        {moduleId === 'health-monitor' && <PeekingProtectionInsights experimentKey={selectedExperiment} />}
        {moduleId === 'sequential-testing' && <LiftTrajectoryInsights experimentKey={selectedExperiment} />}
        {moduleId === 'audience-selection' && <StoreMatchingInsights experimentKey={selectedExperiment} />}
      </div>
    )
  }

  if (channel === 'store' && FOUNDATION_MODULE_IDS.includes(moduleId)) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="type-title">{displayLabel}</h2>
            <span className="rounded-lg border border-border-muted/25 bg-surface-hover px-2 py-0.5 text-xs text-text-secondary">
              {mod.phaseLabel}
            </span>
          </div>
        </div>
        <FoundationDiscoveryInsights moduleKey={moduleId as FoundationModuleKey} />
      </div>
    )
  }

  if (channel === 'store' && CAUSAL_ROI_MODULE_IDS.includes(moduleId)) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="type-title">{displayLabel}</h2>
            <span className="rounded-lg border border-border-muted/25 bg-surface-hover px-2 py-0.5 text-xs text-text-secondary">
              {mod.phaseLabel}
            </span>
          </div>
        </div>
        {moduleId === 'causal-did' && <CausalInferenceInsightsChart experimentKey={selectedExperiment} />}
        {moduleId === 'forecasting' && <ForecastingInsightsChart experimentKey={selectedExperiment} />}
        {moduleId === 'roi-synthesis' && <RoiSynthesisWaterfallChart experimentKey={selectedExperiment} />}
        {moduleId === 'simpsons-paradox' && <SimpsonsParadoxInsightsChart experimentKey={selectedExperiment} />}
        {moduleId === 'learnings-repository' && <LearningsRepositoryInsights />}
      </div>
    )
  }

  if (channel === 'store') {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="type-title">{displayLabel}</h2>
            <span className="rounded-lg border border-border-muted/25 bg-surface-hover px-2 py-0.5 text-xs text-text-secondary">
              {mod.phaseLabel}
            </span>
          </div>
        </div>
        <div className="mx-auto max-w-xl rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-4 py-4">
          <div className="flex items-center gap-2">
            <AppIcon icon={Store} size="sm" className="text-border-muted" />
            <p className="text-sm font-semibold text-text-primary">Results shown in the module panel</p>
          </div>
          <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">
            Store experiment results for {displayLabel} render directly in its configuration panel (in the
            Analytics Lab, right-hand side) as pass/fail evidence specific to this test — not as generic
            web-traffic charts. Open this module from the Chat tab to run it and see results there.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="type-title">{displayLabel}</h2>
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
