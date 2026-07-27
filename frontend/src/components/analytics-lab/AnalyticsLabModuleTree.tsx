import { useEffect, useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useConversationalLoop } from '../../context/ConversationalLoopContext'
import { getModuleIcon, getPhaseIcon } from '../../data/moduleIcons'
import { MODULE_PHASES, type ModulePhaseId } from '../../data/moduleRegistry'
import {
  getRecommendedModuleId,
  isWorkflowStepId,
} from '../../data/hypothesisWorkflow'
import { AppIcon } from '../shared/AppIcon'

const PHASE_SHORT_LABELS: Record<ModulePhaseId, string> = {
  foundation: 'Foundation',
  preplanning: 'Pre-Planning',
  monitoring: 'Monitoring',
  causal: 'Causal & ROI',
}

export function AnalyticsLabModuleTree() {
  const {
    labModuleId,
    selectedExperiment,
    moduleRunsByExperiment,
    workflowProgressByExperiment,
    experimentSpecsByName,
  } = useMatchView()
  const { activeModuleContext, activateModuleContext } = useConversationalLoop()
  const hasSpec = Boolean(experimentSpecsByName[selectedExperiment])
  const [selectedPhaseId, setSelectedPhaseId] = useState<ModulePhaseId>(
    hasSpec ? 'preplanning' : 'foundation',
  )

  const experimentRuns = moduleRunsByExperiment[selectedExperiment] ?? []
  const progress = workflowProgressByExperiment[selectedExperiment] ?? {}
  const recommendedModuleId = hasSpec ? getRecommendedModuleId(progress) : null
  const runCountByModule = experimentRuns.reduce<Record<string, number>>((acc, run) => {
    acc[run.moduleId] = (acc[run.moduleId] ?? 0) + 1
    return acc
  }, {})

  const activeModuleId = activeModuleContext?.moduleId ?? labModuleId

  useEffect(() => {
    if (!activeModuleId) return
    const group = MODULE_PHASES.find((g) => g.modules.some((m) => m.id === activeModuleId))
    if (group) setSelectedPhaseId(group.id)
  }, [activeModuleId])

  const selectedPhase =
    MODULE_PHASES.find((g) => g.id === selectedPhaseId) ?? MODULE_PHASES[0]

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3.5 overflow-hidden">
      <div
        className="grid shrink-0 grid-cols-2 gap-2"
        role="tablist"
        aria-label="Module categories"
      >
        {MODULE_PHASES.map((group) => {
          const isSelected = group.id === selectedPhaseId
          const hasActiveModule = group.modules.some((m) => m.id === activeModuleId)
          const PhaseIcon = getPhaseIcon(group.id)

          return (
            <button
              key={group.id}
              type="button"
              role="tab"
              aria-selected={isSelected}
              title={group.label}
              onClick={() => setSelectedPhaseId(group.id)}
              className={`focus-ring group relative flex flex-col items-start gap-2 overflow-hidden rounded-[8px] border px-2.5 py-2.5 text-left transition-all duration-150 ${
                isSelected
                  ? 'border-transparent bg-gradient-to-br from-border-muted to-rail-hover text-white shadow-[0_6px_16px_rgba(59,130,246,0.28)]'
                  : 'border-border-muted/12 bg-surface-base hover:border-border-muted/30 hover:bg-surface-hover hover:shadow-sm'
              }`}
            >
              {isSelected && (
                <span
                  className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/20 via-transparent to-black/10"
                  aria-hidden="true"
                />
              )}
              {!isSelected && (
                <span
                  className="pointer-events-none absolute -right-3 -top-3 h-12 w-12 rounded-full bg-border-muted/[0.06] transition-colors group-hover:bg-border-muted/10"
                  aria-hidden="true"
                />
              )}
              <div className="relative flex w-full items-center justify-between gap-1">
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-md ${
                    isSelected
                      ? 'bg-white/20'
                      : hasActiveModule
                        ? 'bg-border-muted/12'
                        : 'bg-surface-hover'
                  }`}
                >
                  <AppIcon
                    icon={PhaseIcon}
                    size="sm"
                    className={
                      isSelected
                        ? 'text-white'
                        : hasActiveModule
                          ? 'text-border-muted'
                          : 'text-text-secondary'
                    }
                  />
                </span>
                <span
                  className={`rounded-full px-1.5 py-0.5 text-micro font-semibold tabular-nums ${
                    isSelected
                      ? 'bg-white/20 text-white'
                      : 'bg-surface-hover text-text-secondary'
                  }`}
                >
                  {group.modules.length}
                </span>
              </div>
              <span
                className={`relative line-clamp-2 text-xs font-semibold leading-tight tracking-tight ${
                  isSelected ? 'text-white' : 'text-text-primary'
                }`}
              >
                {PHASE_SHORT_LABELS[group.id]}
              </span>
            </button>
          )
        })}
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[8px] border border-border-muted/10 bg-surface-base/60">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-muted/10 px-3 py-2">
          <p className="type-overline truncate">
            {selectedPhase.label}
          </p>
          <span className="type-micro shrink-0 tabular-nums">
            {selectedPhase.modules.length} modules
          </span>
        </div>
        <ul className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-1.5">
          {selectedPhase.modules.map((mod) => {
            const isActive = mod.id === activeModuleId
            const isRecommended = mod.id === recommendedModuleId
            const isComplete = isWorkflowStepId(mod.id) && Boolean(progress[mod.id])
            const runCount = runCountByModule[mod.id] ?? 0
            const ModIcon = getModuleIcon(mod.id)

            return (
              <li key={mod.id}>
                <button
                  type="button"
                  onClick={() => activateModuleContext(mod.id)}
                  className={`focus-ring group flex w-full items-center gap-2.5 rounded-none px-2 py-2 text-left transition-all duration-150 ${
                    isActive
                      ? 'bg-border-muted/[0.08] shadow-[inset_3px_0_0_0_var(--color-border-muted)]'
                      : isRecommended
                        ? 'bg-surface-hover/80 ring-1 ring-inset ring-border-muted/25 hover:bg-surface-hover'
                        : 'hover:bg-surface-hover'
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center transition-colors ${
                      isActive || isRecommended
                        ? 'text-border-muted'
                        : 'text-text-secondary group-hover:text-border-muted'
                    }`}
                  >
                    <AppIcon icon={ModIcon} size="sm" className="text-inherit" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className={`block truncate text-xs leading-tight ${
                        isActive ? 'font-semibold text-text-primary' : 'font-medium text-text-primary'
                      }`}
                    >
                      {mod.label}
                    </span>
                    {isRecommended && !isComplete ? (
                      <span className="mt-0.5 block text-micro font-medium text-border-muted">
                        Recommended next
                      </span>
                    ) : null}
                  </span>
                  {(isComplete || runCount > 0) && (
                    <span
                      className={`flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-micro font-medium ${
                        isComplete
                          ? 'bg-green-50 text-green-700'
                          : 'bg-surface-hover text-text-secondary'
                      }`}
                    >
                      <AppIcon icon={CheckCircle2} size="xs" />
                      {isComplete ? 'Done' : runCount}
                    </span>
                  )}
                  {isActive ? (
                    <span
                      className="h-2 w-2 shrink-0 rounded-full bg-border-muted"
                      aria-hidden="true"
                    />
                  ) : null}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
