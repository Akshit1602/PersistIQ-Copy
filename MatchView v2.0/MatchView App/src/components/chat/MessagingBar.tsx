import { useRef, useState } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useConversationalLoop } from '../../context/ConversationalLoopContext'
import { getActionPills } from '../../data/moduleRegistry'
import { parseInterviewAnswerFromText } from '../../data/moduleInterviewEngine'
import type { InterviewPill } from '../../context/conversationalLoopTypes'
import type { ModuleId } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'
import { PhaseDropdown } from './PhaseDropdown'
import { ActionPills } from './ActionPills'
import { SmartActionPhasePills } from './SmartActionPhasePills'

export function MessagingBar() {
  const { currentPersona, activePhase, activeModuleId, sendMessage, executePill, advanceToWorkflowStep, isLlmProcessing } =
    useMatchView()
  const {
    activeModuleContext,
    interviewPhase,
    pendingFieldKey,
    smartPills,
    submitInterviewAnswer,
    executeSimulation,
  } = useConversationalLoop()
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const inInterview =
    currentPersona === 'analyst' &&
    activeModuleContext !== null &&
    (interviewPhase === 'interviewing' ||
      interviewPhase === 'ready' ||
      interviewPhase === 'complete')

  const genericPills = inInterview ? [] : getActionPills(currentPersona, activePhase, activeModuleId)

  const handlePillClick = (prompt: string) => {
    if (currentPersona === 'analyst') {
      executePill(prompt)
      return
    }
    setInputValue(prompt)
    inputRef.current?.focus()
  }

  const handleSmartPillSelect = (pill: InterviewPill) => {
    if (pill.fieldKey === '__run__') {
      executeSimulation()
      return
    }
    if (pill.fieldKey === '__proceed__') {
      const raw = String(pill.value)
      const moduleId = raw.startsWith('__proceed__:')
        ? (raw.slice('__proceed__:'.length) as ModuleId)
        : null
      if (moduleId) advanceToWorkflowStep(moduleId)
      return
    }
    submitInterviewAnswer(pill.fieldKey, pill.value, pill.label)
  }

  const handleSend = () => {
    const trimmed = inputValue.trim()
    if (!trimmed) return

    if (inInterview && pendingFieldKey && activeModuleContext) {
      const parsed = parseInterviewAnswerFromText(
        activeModuleContext.moduleId,
        pendingFieldKey,
        trimmed,
      )
      if (parsed !== null) {
        submitInterviewAnswer(pendingFieldKey, parsed, trimmed)
        setInputValue('')
        return
      }
    }

    sendMessage(trimmed)
    setInputValue('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="shrink-0 border-t border-border-muted/20 px-5 py-3">
      {inInterview ? (
        <SmartActionPhasePills pills={smartPills} onPillSelect={handleSmartPillSelect} />
      ) : (
        <ActionPills pills={genericPills} onPillClick={handlePillClick} />
      )}
      <div className="flex items-center gap-1.5 rounded-sm border border-border-muted/30 bg-surface-raised p-1.5">
        <PhaseDropdown />
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLlmProcessing}
          placeholder={
            isLlmProcessing
              ? 'Agent is processing…'
              : inInterview && pendingFieldKey
                ? 'Type your answer or pick a pill above…'
                : 'Type your conversational query...'
          }
          className={`focus-ring min-w-0 flex-1 bg-transparent px-1.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary ${
            isLlmProcessing ? 'cursor-not-allowed opacity-50' : ''
          }`}
          aria-label="Conversational query input"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!inputValue.trim() || isLlmProcessing}
          className="focus-ring flex shrink-0 items-center gap-1 rounded-xs bg-border-muted px-2.5 py-1.5 text-xs font-medium text-white transition-opacity duration-instant hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Send message"
        >
          {isLlmProcessing ? (
            <AppIcon icon={Loader2} size="xs" className="animate-spin" />
          ) : (
            <AppIcon icon={Send} size="xs" />
          )}
          {isLlmProcessing ? 'Processing' : 'Send'}
        </button>
      </div>
    </div>
  )
}
