import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { formatMessageTime } from '../data/mock'
import {
  bootstrapModuleParams,
  buildAutoFillSummary,
  buildReadyMessage,
  getNextInterviewStep,
  getSmartPillsForPhase,
} from '../data/moduleInterviewEngine'
import {
  buildBriefBody,
  buildExperimentTypeDefaults,
  buildMetricsFormDefaults,
} from '../data/briefBuilder'
import { suggestFieldValues } from '../data/inputSuggestions'
import { MODULE_BY_ID } from '../data/moduleRegistry'
import type { ModuleId, TextChatMessage } from './types'
import { isModuleRunMessage } from './types'
import { useMatchView } from './MatchViewContext'
import type {
  ActiveModuleContext,
  ConversationalLoopContextValue,
  InterviewPhase,
  InterviewPill,
} from './conversationalLoopTypes'

const ConversationalLoopContext = createContext<ConversationalLoopContextValue | null>(null)

let loopMessageCounter = 500

function nextLoopMessageId() {
  loopMessageCounter += 1
  return `lm${loopMessageCounter}`
}

export function ConversationalLoopProvider({ children }: { children: ReactNode }) {
  const {
    activeThreadId,
    selectedExperiment,
    moduleRunStatus,
    messagesByThread,
    pendingModuleActivation,
    experimentSpecsByName,
    moduleFormValuesByExperiment,
    setTab,
    selectLabModule,
    updateModuleFormField,
    injectNlpParameters,
    runModule,
    setActivePhase,
    appendChatMessages,
    clearPendingModuleActivation,
    openAudienceWizard,
    getSuggestionContext,
  } = useMatchView()

  const [activeModuleContext, setActiveModuleContext] = useState<ActiveModuleContext | null>(null)
  const [interviewPhase, setInterviewPhase] = useState<InterviewPhase>('idle')
  const [pendingFieldKey, setPendingFieldKey] = useState<string | null>(null)
  const [confirmedFieldKeys, setConfirmedFieldKeys] = useState<string[]>([])

  const interviewRef = useRef({ confirmedFieldKeys, interviewPhase, activeModuleContext })
  interviewRef.current = { confirmedFieldKeys, interviewPhase, activeModuleContext }

  const appendMessages = useCallback(
    (messages: TextChatMessage[]) => {
      if (!activeThreadId || messages.length === 0) return
      appendChatMessages(messages)
    },
    [activeThreadId, appendChatMessages],
  )

  const askNextQuestion = useCallback(
    (moduleId: ModuleId, confirmed: string[]) => {
      const next = getNextInterviewStep(moduleId, confirmed)
      if (!next) {
        setInterviewPhase('ready')
        setPendingFieldKey(null)
        appendMessages([
          {
            kind: 'text',
            id: nextLoopMessageId(),
            role: 'assistant',
            content: buildReadyMessage(moduleId),
            timestamp: formatMessageTime(),
          },
        ])
        return
      }
      setPendingFieldKey(next.fieldKey)
      setInterviewPhase('interviewing')
      appendMessages([
        {
          kind: 'text',
          id: nextLoopMessageId(),
          role: 'assistant',
          content: next.question,
          timestamp: formatMessageTime(),
        },
      ])
    },
    [appendMessages],
  )

  const activateModuleContext = useCallback(
    (moduleId: ModuleId) => {
      if (moduleId === 'audience-selection') {
        setTab('chat')
        setActivePhase(moduleId)
        selectLabModule(moduleId)
        openAudienceWizard()
        return
      }

      const mod = MODULE_BY_ID[moduleId]
      const now = formatMessageTime()
      const spec = experimentSpecsByName[selectedExperiment]
      const existing = moduleFormValuesByExperiment[selectedExperiment]?.[moduleId]

      setTab('chat')
      setActivePhase(moduleId)
      selectLabModule(moduleId)

      let seed = existing ? { ...existing } : undefined
      if (!seed && spec && moduleId === 'metrics-tracking') {
        const sizing = moduleFormValuesByExperiment[selectedExperiment]?.['opportunity-sizing']
        const expectedLift =
          typeof sizing?.expectedLift === 'number' ? sizing.expectedLift : undefined
        seed = buildMetricsFormDefaults(spec.hypothesis, spec.goal, {
          expectedLift,
          addressableVolume:
            typeof sizing?.monthlyInquiries === 'number'
              ? sizing.monthlyInquiries
              : typeof sizing?.addressableVolume === 'number'
                ? sizing.addressableVolume
                : undefined,
          currentInteractionRate:
            typeof sizing?.currentIor === 'number'
              ? sizing.currentIor * 100
              : typeof sizing?.currentInteractionRate === 'number'
                ? sizing.currentInteractionRate
                : undefined,
          targetInteractionRate:
            typeof sizing?.targetIor === 'number'
              ? sizing.targetIor * 100
              : typeof sizing?.targetInteractionRate === 'number'
                ? sizing.targetInteractionRate
                : undefined,
        })
      }
      if (!seed && spec && moduleId === 'experiment-type') {
        const sizing = moduleFormValuesByExperiment[selectedExperiment]?.['opportunity-sizing']
        seed = buildExperimentTypeDefaults(spec.hypothesis, spec.goal, {
          expectedLift:
            typeof sizing?.expectedLift === 'number' ? sizing.expectedLift : undefined,
          addressableVolume:
            typeof sizing?.monthlyInquiries === 'number'
              ? sizing.monthlyInquiries
              : typeof sizing?.addressableVolume === 'number'
                ? sizing.addressableVolume
                : undefined,
          currentInteractionRate:
            typeof sizing?.currentIor === 'number'
              ? sizing.currentIor * 100
              : typeof sizing?.currentInteractionRate === 'number'
                ? sizing.currentInteractionRate
                : undefined,
          targetInteractionRate:
            typeof sizing?.targetIor === 'number'
              ? sizing.targetIor * 100
              : typeof sizing?.targetInteractionRate === 'number'
                ? sizing.targetInteractionRate
                : undefined,
        })
      }
      if (spec && moduleId === 'brief-generator') {
        const snapshots = moduleFormValuesByExperiment[selectedExperiment] ?? {}
        seed = {
          ...(existing ?? {}),
          briefTitle: `${spec.name} — Digital Experiment Brief`,
          briefBody: buildBriefBody(spec, snapshots),
        }
      }

      const suggestionContext = getSuggestionContext(selectedExperiment)
      const { params, autoFilledFields } = bootstrapModuleParams(
        moduleId,
        selectedExperiment,
        seed,
        suggestionContext,
      )
      injectNlpParameters(moduleId, params, autoFilledFields)

      // Suggested seeds count as auto-filled so interview skips those turns
      const confirmed = autoFilledFields
      setActiveModuleContext({ moduleId, label: mod.label, startedAt: now })
      setConfirmedFieldKeys(confirmed)
      setInterviewPhase('interviewing')
      setPendingFieldKey(null)

      appendMessages([
        {
          kind: 'text',
          id: nextLoopMessageId(),
          role: 'assistant',
          content: buildAutoFillSummary(
            moduleId,
            selectedExperiment,
            autoFilledFields,
            params,
            suggestionContext.channel,
            suggestFieldValues(moduleId, suggestionContext),
          ),
          timestamp: now,
        },
      ])

      window.setTimeout(() => askNextQuestion(moduleId, confirmed), 80)
    },
    [
      setTab,
      setActivePhase,
      selectLabModule,
      openAudienceWizard,
      selectedExperiment,
      experimentSpecsByName,
      moduleFormValuesByExperiment,
      injectNlpParameters,
      appendMessages,
      askNextQuestion,
      getSuggestionContext,
    ],
  )

  const submitInterviewAnswer = useCallback(
    (fieldKey: string, value: unknown, label?: string) => {
      const ctx = interviewRef.current.activeModuleContext
      if (!ctx || interviewRef.current.interviewPhase === 'running') return

      const display = label ?? String(value)
      appendMessages([
        {
          kind: 'text',
          id: nextLoopMessageId(),
          role: 'user',
          content: display,
          timestamp: formatMessageTime(),
        },
      ])

      updateModuleFormField(ctx.moduleId, fieldKey, value)

      const nextConfirmed = interviewRef.current.confirmedFieldKeys.includes(fieldKey)
        ? interviewRef.current.confirmedFieldKeys
        : [...interviewRef.current.confirmedFieldKeys, fieldKey]

      setConfirmedFieldKeys(nextConfirmed)
      askNextQuestion(ctx.moduleId, nextConfirmed)
    },
    [appendMessages, updateModuleFormField, askNextQuestion],
  )

  const executeSimulation = useCallback(() => {
    const ctx = interviewRef.current.activeModuleContext
    if (!ctx || moduleRunStatus === 'running') return

    setInterviewPhase('running')
    setPendingFieldKey(null)

    appendMessages([
      {
        kind: 'text',
        id: nextLoopMessageId(),
        role: 'user',
        content: '🚀 Run Simulation Now',
        timestamp: formatMessageTime(),
      },
    ])

    runModule(ctx.moduleId, { skipUserMessage: true })
  }, [moduleRunStatus, appendMessages, runModule])

  const pushResultsToInsights = useCallback(() => {
    const ctx = interviewRef.current.activeModuleContext
    if (ctx) {
      selectLabModule(ctx.moduleId)
    }
    setTab('insights')
  }, [setTab, selectLabModule])

  useEffect(() => {
    setActiveModuleContext(null)
    setInterviewPhase('idle')
    setPendingFieldKey(null)
    setConfirmedFieldKeys([])
  }, [activeThreadId])

  useEffect(() => {
    if (!pendingModuleActivation) return
    const moduleId = pendingModuleActivation
    clearPendingModuleActivation()
    // Defer so thread/messages from createExperiment are committed first
    window.setTimeout(() => activateModuleContext(moduleId), 50)
  }, [pendingModuleActivation, clearPendingModuleActivation, activateModuleContext])

  useEffect(() => {
    if (!activeModuleContext || interviewPhase !== 'running') return
    if (moduleRunStatus !== 'success') return

    const messages = messagesByThread[activeThreadId] ?? []
    const hasResult = messages.some(
      (m) =>
        isModuleRunMessage(m) &&
        m.moduleId === activeModuleContext.moduleId &&
        m.status === 'success',
    )
    if (hasResult) {
      setInterviewPhase('complete')
    }
  }, [moduleRunStatus, activeModuleContext, interviewPhase, messagesByThread, activeThreadId])

  const smartPills = useMemo((): InterviewPill[] => {
    if (!activeModuleContext) return []
    return getSmartPillsForPhase(
      activeModuleContext.moduleId,
      confirmedFieldKeys,
      interviewPhase,
      getSuggestionContext(selectedExperiment),
    )
  }, [
    activeModuleContext,
    confirmedFieldKeys,
    interviewPhase,
    getSuggestionContext,
    selectedExperiment,
  ])

  const value = useMemo<ConversationalLoopContextValue>(
    () => ({
      activeModuleContext,
      interviewPhase,
      pendingFieldKey,
      confirmedFieldKeys,
      smartPills,
      activateModuleContext,
      submitInterviewAnswer,
      executeSimulation,
      pushResultsToInsights,
    }),
    [
      activeModuleContext,
      interviewPhase,
      pendingFieldKey,
      confirmedFieldKeys,
      smartPills,
      activateModuleContext,
      submitInterviewAnswer,
      executeSimulation,
      pushResultsToInsights,
    ],
  )

  return (
    <ConversationalLoopContext.Provider value={value}>{children}</ConversationalLoopContext.Provider>
  )
}

export function useConversationalLoop(): ConversationalLoopContextValue {
  const ctx = useContext(ConversationalLoopContext)
  if (!ctx) {
    throw new Error('useConversationalLoop must be used within ConversationalLoopProvider')
  }
  return ctx
}
