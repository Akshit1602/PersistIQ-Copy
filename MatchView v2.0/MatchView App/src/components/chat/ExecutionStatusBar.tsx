import { Loader2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useConversationalLoop } from '../../context/ConversationalLoopContext'
import { isModuleRunMessage, type ModuleRunChatMessage } from '../../context/types'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'

export function ExecutionStatusBar() {
  const { moduleRunStatus, messagesByThread, activeThreadId } = useMatchView()
  const { interviewPhase, activeModuleContext } = useConversationalLoop()

  const isActive = moduleRunStatus === 'running' || interviewPhase === 'running'
  if (!isActive) return null

  const messages = messagesByThread[activeThreadId] ?? []
  const runningMessage = [...messages]
    .reverse()
    .find((m): m is ModuleRunChatMessage => isModuleRunMessage(m) && m.status === 'running')

  const moduleLabel =
    activeModuleContext?.label ??
    (runningMessage ? MODULE_BY_ID[runningMessage.moduleId].label : 'Module')

  const latestLog = runningMessage?.logs[runningMessage.logs.length - 1]

  return (
    <div
      className="shrink-0 border-t border-border-muted/25 bg-[#1a1d24] px-5 py-2"
      role="status"
      aria-live="polite"
      style={{ transform: 'translateZ(0)' }}
    >
      <div className="flex items-center gap-3">
        <AppIcon icon={Loader2} size="xs" className="shrink-0 animate-spin text-amber-400" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-white/90">
            Executing {moduleLabel} simulation…
          </p>
          {latestLog && (
            <p className="mt-0.5 truncate font-mono text-micro text-white/50">{latestLog}</p>
          )}
        </div>
        {runningMessage && runningMessage.logs.length > 0 && (
          <span className="shrink-0 rounded-md bg-white/10 px-2 py-0.5 text-micro tabular-nums text-white/60">
            {runningMessage.logs.length} steps
          </span>
        )}
      </div>
    </div>
  )
}
