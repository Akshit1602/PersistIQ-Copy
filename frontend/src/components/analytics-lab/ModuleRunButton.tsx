import { useMatchView } from '../../context/MatchViewContext'
import type { ModuleId } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'
import { Loader2, Play } from 'lucide-react'

interface ModuleRunButtonProps {
  moduleId: ModuleId
}

export function ModuleRunButton({ moduleId }: ModuleRunButtonProps) {
  const { moduleRunStatus, runModule } = useMatchView()
  const isRunning = moduleRunStatus === 'running'

  return (
    <button
      type="button"
      onClick={() => runModule(moduleId)}
      disabled={isRunning}
      className="focus-ring flex w-full items-center justify-center gap-1.5 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white shadow-glow transition-opacity duration-instant hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {isRunning ? (
        <>
          <AppIcon icon={Loader2} size="xs" className="animate-spin" />
          Executing…
        </>
      ) : (
        <>
          <AppIcon icon={Play} size="xs" />
          Run Analytical Model
        </>
      )}
    </button>
  )
}
