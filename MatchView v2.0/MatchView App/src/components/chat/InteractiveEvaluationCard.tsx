import { ArrowUpRight, Loader2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { ModuleRunChatMessage } from '../../context/types'
import { getModuleIcon } from '../../data/moduleIcons'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'
import { PowerEvaluationCard } from './PowerEvaluationCard'

interface InteractiveEvaluationCardProps {
  message: ModuleRunChatMessage
}

export function InteractiveEvaluationCard({ message }: InteractiveEvaluationCardProps) {
  const { selectLabModule, setTab } = useMatchView()

  const mod = MODULE_BY_ID[message.moduleId]
  const ModIcon = getModuleIcon(message.moduleId)
  const isRunning = message.status === 'running'
  const isComplete = message.status === 'success'
  const isError = message.status === 'error'

  const statusLabel = isRunning ? 'Running' : isComplete ? 'Complete' : 'Failed'
  const statusClass = isRunning
    ? 'bg-amber-500/12 text-amber-700'
    : isComplete
      ? 'bg-emerald-500/12 text-emerald-700'
      : 'bg-red-500/12 text-red-700'

  const hasPowerCurve =
    isComplete && message.evaluation?.type === 'power-curve' && message.evaluation.powerCurve

  const openInsights = () => {
    selectLabModule(message.moduleId)
    setTab('insights')
  }

  return (
    <article className="glass-panel w-full max-w-[min(100%,440px)] overflow-hidden rounded-sm">
      <header className="flex items-start gap-2 border-b border-border-muted/10 px-3 py-2">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-xs bg-surface-hover">
          <AppIcon icon={ModIcon} size="xs" className="text-border-muted" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
            <h3 className="text-xs font-semibold text-text-primary">{mod.label}</h3>
            <span
              className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-micro font-medium uppercase tracking-wide ${statusClass}`}
            >
              {isRunning && (
                <AppIcon icon={Loader2} size="xs" className="mr-1 animate-spin" />
              )}
              {statusLabel}
            </span>
            {message.duration && (
              <span className="text-micro tabular-nums text-text-secondary">{message.duration}</span>
            )}
          </div>
          {isRunning && (
            <p className="mt-0.5 text-xs text-text-secondary">Running with locked parameters…</p>
          )}
          {isError && message.evaluation?.summary && (
            <p className="mt-0.5 text-xs text-red-600">{message.evaluation.summary}</p>
          )}
          {isComplete && !hasPowerCurve && message.evaluation?.summary && (
            <p className="mt-0.5 text-xs leading-relaxed text-text-secondary">
              {message.evaluation.summary}
            </p>
          )}
        </div>
        <time className="shrink-0 text-micro tabular-nums text-text-secondary">
          {message.timestamp}
        </time>
      </header>

      {hasPowerCurve && (
        <div className="px-3 py-2.5">
          <PowerEvaluationCard
            evaluation={message.evaluation!.powerCurve!}
            onOpenInsights={openInsights}
          />
        </div>
      )}

      {isComplete && message.evaluation?.type === 'generic' && (
        <footer className="border-t border-border-muted/10 px-3 py-1.5">
          <button
            type="button"
            onClick={openInsights}
            className="focus-ring group flex items-center gap-1 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            View full matrix in Insights
            <AppIcon
              icon={ArrowUpRight}
              size="xs"
              className="transition-transform group-hover:-translate-y-px group-hover:translate-x-px"
            />
          </button>
        </footer>
      )}
    </article>
  )
}
