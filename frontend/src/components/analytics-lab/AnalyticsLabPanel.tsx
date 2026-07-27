import { ArrowLeft, ChevronLeft, FlaskConical, History, LayoutList, PanelRightClose, Settings2 } from 'lucide-react'
import { ANALYTICS_LAB_COLLAPSED_WIDTH, ANALYTICS_LAB_WIDTH } from '../../constants/layout'
import { useMatchView } from '../../context/MatchViewContext'
import type { LabPanelView } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'
import { AnalyticsLabModuleTree } from './AnalyticsLabModuleTree'
import { LabRunHistory } from './LabRunHistory'
import { ModuleConfigForm } from './ModuleConfigForm'

const VIEW_TABS: { id: LabPanelView; label: string; icon: typeof LayoutList }[] = [
  { id: 'tree', label: 'Modules', icon: LayoutList },
  { id: 'runs', label: 'Results', icon: History },
]

function LabFormToolbar() {
  const { resetLabToTree } = useMatchView()

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={resetLabToTree}
        className="focus-ring inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border-muted/20 bg-surface-base px-2.5 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-muted/35 hover:bg-surface-hover hover:text-text-primary"
        aria-label="Back to modules"
      >
        <AppIcon icon={ArrowLeft} size="xs" />
        Back
      </button>
      <div className="min-w-0 flex-1" aria-hidden="true" />
      <button
        type="button"
        aria-current="page"
        className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border-muted/20 bg-surface-base text-text-secondary transition-colors hover:border-border-muted/40 hover:bg-surface-hover hover:text-text-primary"
        aria-label="Configure module"
        title="Configure"
      >
        <AppIcon icon={Settings2} size="xs" />
      </button>
    </div>
  )
}

export function AnalyticsLabPanel() {
  const {
    labPanelView,
    labModuleId,
    selectedExperiment,
    analyticsLabCollapsed,
    toggleAnalyticsLabCollapsed,
    setLabPanelView,
    moduleRunsByExperiment,
  } = useMatchView()

  const runCount = (moduleRunsByExperiment[selectedExperiment] ?? []).length

  if (analyticsLabCollapsed) {
    return (
      <aside
        className="lab-panel h-full min-h-0 shrink-0 self-stretch border-r border-border-muted/10"
        style={{ width: ANALYTICS_LAB_COLLAPSED_WIDTH }}
      >
        <button
          type="button"
          onClick={toggleAnalyticsLabCollapsed}
          className="focus-ring flex h-full w-full cursor-pointer flex-col items-center py-3 transition-colors hover:bg-surface-hover"
          aria-label="Expand Advanced Analytics Lab"
          title="Expand Analytics Lab"
        >
          <AppIcon icon={ChevronLeft} size="sm" className="mb-4 text-text-secondary" />
          <div className="flex flex-1 flex-col items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-border-muted/15">
              <AppIcon icon={FlaskConical} size="sm" className="text-border-muted" />
            </span>
            <span
              className="text-micro font-semibold uppercase tracking-wide text-text-secondary"
              style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
            >
              Lab
            </span>
          </div>
        </button>
      </aside>
    )
  }

  const isForm = labPanelView === 'form'

  return (
    <aside
      className="lab-panel flex shrink-0 flex-col overflow-hidden border-r border-border-muted/10"
      style={{ width: ANALYTICS_LAB_WIDTH }}
      aria-label="Advanced Analytics Lab"
    >
      <header className="relative shrink-0 overflow-hidden border-b border-border-muted/12 px-3 pb-3 pt-3">
        <div
          className="pointer-events-none absolute inset-0 bg-gradient-to-br from-border-muted/[0.07] via-transparent to-transparent"
          aria-hidden="true"
        />
        <div className="relative flex items-center gap-2.5">
          <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-border-muted to-rail-hover shadow-[0_4px_12px_rgba(59,130,246,0.28)]">
            <AppIcon icon={FlaskConical} size="sm" className="text-white" />
            <span
              className="pointer-events-none absolute inset-0 rounded-md bg-gradient-to-br from-white/25 via-transparent to-transparent"
              aria-hidden="true"
            />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="type-title">
              Analytics Lab
            </h2>
            <p className="type-subtitle mt-0.5">Modules & experiment results</p>
          </div>
          <button
            type="button"
            onClick={toggleAnalyticsLabCollapsed}
            className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
            aria-label="Collapse Analytics Lab"
            title="Collapse panel"
          >
            <AppIcon icon={PanelRightClose} size="sm" />
          </button>
        </div>

        <div className="relative mt-3">
          {isForm ? (
            <LabFormToolbar />
          ) : (
            <div className="flex rounded-md border border-border-muted/15 bg-surface-base/80 p-1 shadow-sm">
              {VIEW_TABS.map((tab) => {
                const isActive = labPanelView === tab.id
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setLabPanelView(tab.id)}
                    className={`focus-ring flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-medium transition-all duration-150 ${
                      isActive
                        ? 'bg-rail-hover text-white shadow-sm'
                        : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
                    }`}
                  >
                    <AppIcon icon={tab.icon} size="xs" />
                    {tab.label}
                    {tab.id === 'runs' && runCount > 0 && (
                      <span
                        className={`rounded-full px-1.5 py-px tabular-nums text-micro font-semibold ${
                          isActive ? 'bg-white/20 text-white' : 'bg-border-muted/10 text-border-muted'
                        }`}
                      >
                        {runCount}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </header>

      <div
        className={`flex min-h-0 flex-1 flex-col overflow-hidden ${
          isForm ? 'bg-surface-base' : 'p-3'
        }`}
      >
        {labPanelView === 'tree' && <AnalyticsLabModuleTree />}
        {labPanelView === 'runs' && <LabRunHistory />}
        {labPanelView === 'form' && labModuleId && <ModuleConfigForm moduleId={labModuleId} />}
      </div>
    </aside>
  )
}
