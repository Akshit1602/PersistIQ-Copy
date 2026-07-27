import { useMatchView } from '../../context/MatchViewContext'
import { MOCK_CHARTS } from '../../data/mock'
import { ChartCard } from '../insights/ChartCard'
import { ChartDetectiveDrawer } from '../insights/ChartDetectiveDrawer'
import { InsightsDashboardGrid } from '../insights/InsightsDashboardGrid'
import { ExposureTrendCard } from '../insights/ExposureTrendCard'
import { MetricSheetCard } from '../insights/MetricSheetCard'
import { ModuleInsightsScreen } from '../insights/ModuleInsightsScreen'
import { SegmentConversionCard } from '../insights/SegmentConversionCard'

function DefaultInsightsDashboard() {
  const [featured, ...rest] = MOCK_CHARTS

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <InsightsDashboardGrid featured={<ChartCard chart={featured} featured />}>
        <ExposureTrendCard />
        <SegmentConversionCard />
        <MetricSheetCard />
        {rest.map((chart) => (
          <ChartCard key={chart.id} chart={chart} />
        ))}
      </InsightsDashboardGrid>
    </div>
  )
}

export function InsightsView() {
  const { activeModuleId } = useMatchView()

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      {activeModuleId ? (
        <ModuleInsightsScreen moduleId={activeModuleId} />
      ) : (
        <DefaultInsightsDashboard />
      )}
      <ChartDetectiveDrawer />
    </div>
  )
}
