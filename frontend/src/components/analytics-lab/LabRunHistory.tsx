import { CheckCircle2, Clock, ExternalLink } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { getModuleIcon } from '../../data/moduleIcons'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'

export function LabRunHistory() {
  const { selectedExperiment, moduleRunsByExperiment, openModuleRun } = useMatchView()

  const runs = moduleRunsByExperiment[selectedExperiment] ?? []

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center px-4 py-8 text-center">
        <p className="text-sm font-medium text-text-primary">No runs yet</p>
        <p className="mt-1 text-xs text-text-secondary">
          Configure and run a module for this experiment. Results will appear here.
        </p>
      </div>
    )
  }

  return (
    <ul className="flex flex-col gap-1.5 overflow-y-auto">
      {runs.map((run) => {
        const mod = MODULE_BY_ID[run.moduleId]
        const ModIcon = getModuleIcon(run.moduleId)
        return (
          <li key={run.id}>
            <button
              type="button"
              onClick={() => openModuleRun(run.id)}
              className="focus-ring flex w-full items-start gap-2 rounded-xs border border-border-muted/15 bg-surface-raised p-2.5 text-left transition-colors duration-instant hover:border-border-muted/30 hover:bg-surface-hover"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xs bg-surface-hover">
                <AppIcon icon={ModIcon} size="sm" className="text-border-muted" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-medium text-text-primary">{mod.label}</span>
                  {run.status === 'success' && (
                    <AppIcon icon={CheckCircle2} size="xs" className="shrink-0 text-green-600" />
                  )}
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-xs text-text-secondary">
                  <span className="flex items-center gap-1">
                    <AppIcon icon={Clock} size="xs" />
                    {run.completedAt}
                  </span>
                  <span className="tabular-nums">{run.duration}</span>
                </div>
              </div>
              <AppIcon icon={ExternalLink} size="xs" className="mt-1 shrink-0 text-text-secondary" />
            </button>
          </li>
        )
      })}
    </ul>
  )
}
