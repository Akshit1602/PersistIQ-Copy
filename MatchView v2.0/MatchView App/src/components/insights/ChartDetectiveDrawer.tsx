import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { ANALYTICS_LAB_COLLAPSED_WIDTH, ANALYTICS_LAB_WIDTH } from '../../constants/layout'
import { useMatchView } from '../../context/MatchViewContext'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { MOCK_CHARTS } from '../../data/mock'
import { AppIcon } from '../shared/AppIcon'

const CHART_EXPLANATIONS: Record<string, string> = {
  'exposure-trend': 'Daily exposure shows a steady upward trend with treatment group receiving 12% more impressions by day 14.',
  'segment-conversion': 'Mobile and returning customer segments drive the majority of conversion lift at +5.8% and +6.1% respectively.',
  'metric-sheet': 'All primary metrics pass significance thresholds. SRM delta of 0.003 is within acceptable bounds.',
  'chart-lift': 'Treatment group performance exceeded control by a statistically significant margin (p < 0.01).',
  'chart-funnel': 'Funnel drop-off is concentrated at the cart step; treatment reduces abandonment by 2.1pp.',
  'chart-roi': 'Projected annual GMV impact of $4.8M based on current lift trajectory and audience reach.',
  'chart-reach': '2.4M unique users reached with balanced allocation across treatment and control.',
}

export function ChartDetectiveDrawer() {
  const {
    chartDrawerOpen,
    chartDrawerTargetId,
    activeModuleId,
    selectedExperiment,
    closeChartDrawer,
    sendMessage,
    activeThreadId,
    currentPersona,
    analyticsLabCollapsed,
  } = useMatchView()
  const [prompt, setPrompt] = useState('')

  const labRightOffset =
    currentPersona === 'analyst'
      ? analyticsLabCollapsed
        ? ANALYTICS_LAB_COLLAPSED_WIDTH
        : ANALYTICS_LAB_WIDTH
      : 0

  const chart = MOCK_CHARTS.find((c) => c.id === chartDrawerTargetId)
  const mod = activeModuleId ? MODULE_BY_ID[activeModuleId] : null

  const explanation =
    (chartDrawerTargetId && CHART_EXPLANATIONS[chartDrawerTargetId]) ||
    (chart
      ? `The ${chart.title} shows ${chart.metric} ${chart.change}. Treatment group performance exceeded control by a statistically significant margin (p < 0.01).`
      : mod
        ? `Analysis for ${mod.label} within ${selectedExperiment}. Module executed in ${mod.mockDuration} with verified outputs.`
        : 'Select a chart to begin analysis.')

  if (!chartDrawerOpen) return null

  const handleSendToChat = () => {
    const summary = `[Chart Detective — ${chart?.title ?? chartDrawerTargetId ?? mod?.label}]\n${explanation}`
    sendMessage(summary)
    closeChartDrawer()
  }

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-30 bg-black/20 backdrop-blur-[2px]"
        style={labRightOffset ? { right: labRightOffset } : undefined}
        onClick={closeChartDrawer}
        aria-label="Close chart detective drawer"
      />

      <aside
        className={`fixed top-0 z-40 flex h-full w-[30%] min-w-[320px] flex-col border-l border-border-muted/30 glass-panel transition-transform duration-instant ease-in-out ${
          chartDrawerOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
        style={{ right: labRightOffset }}
        aria-label="Chart Detective"
      >
        <header className="flex items-center justify-between border-b border-border-muted/20 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Chart Detective</h2>
            <p className="text-xs text-text-secondary">
              {chart?.title ?? mod?.label ?? 'Chart Analysis'}
              {mod ? ` · ${mod.phaseLabel}` : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={closeChartDrawer}
            className="focus-ring flex h-8 w-8 items-center justify-center rounded-xs text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
            aria-label="Close drawer"
          >
            <AppIcon icon={X} size="sm" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div className="glass-panel rounded-xs p-4">
            <p className="text-sm leading-relaxed text-text-primary">{explanation}</p>
          </div>
        </div>

        <div className="border-t border-border-muted/20 p-4">
          <div className="mb-3 flex gap-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask about this chart..."
              className="focus-ring min-w-0 flex-1 rounded-xs border border-border-muted/30 bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-secondary"
              aria-label="Chart analysis prompt"
            />
            <button
              type="button"
              className="focus-ring shrink-0 rounded-xs bg-border-muted px-3 py-2 text-sm font-medium text-white"
            >
              Ask
            </button>
          </div>
          <button
            type="button"
            onClick={handleSendToChat}
            disabled={!activeThreadId}
            className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs border border-border-muted/40 py-2 text-sm font-medium text-text-primary transition-colors duration-instant hover:bg-surface-hover hover:shadow-glow disabled:opacity-40"
          >
            <AppIcon icon={Plus} size="sm" />
            Send this analysis to Main Chat History
          </button>
        </div>
      </aside>
    </>
  )
}
