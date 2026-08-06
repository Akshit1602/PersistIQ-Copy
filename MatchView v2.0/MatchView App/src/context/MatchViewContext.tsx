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
import { queryFmapiChat, type FmapiChatMessage, type FmapiToolCall } from '../data/fmapiClient'
import { AGENT_TOOLS, getModuleForTool, buildToolCallSummary, toolArgsToModuleParams } from '../data/agentTools'
import {
  buildAssistantReply,
  buildInitialMessages,
  buildWelcomeMessage,
  formatMessageTime,
  INITIAL_ACTIVE_THREAD_ID,
  INITIAL_EXPERIMENT_PROJECT_IDS,
  INITIAL_EXPERIMENTS,
  INITIAL_PROJECTS,
  INITIAL_THREAD_GROUPS,
} from '../data/mock'
import { buildExecutionLogStream } from '../data/executionService'
import { resolveChatIntent } from '../data/chatIntentRouter'
import { buildModuleEvaluation } from '../data/moduleEvaluation'
import { buildInitialReports } from '../data/initialReports'
import { INITIAL_MODULE_RUNS } from '../data/initialModuleRuns'
import { getDefaultFormValues, getModuleFormSchema } from '../data/moduleFormSchemas'
import { MODULE_BY_ID } from '../data/moduleRegistry'
import { computeLiveExperimentStats } from '../data/executiveStats'
import { buildWorkspaceStats } from '../data/workspaceStats'
import {
  buildBriefBody,
  buildExperimentTypeDefaults,
  buildMetricsFormDefaults,
} from '../data/briefBuilder'
import {
  buildSimilarLearningsMessage,
  findSimilarLearnings,
} from '../data/historicalLearnings'
import {
  isWorkflowStepId,
  markStepComplete,
  type WorkflowStepId,
} from '../data/hypothesisWorkflow'
import {
  ANALYST_SUB_PHASES,
  type AuthUser,
  type ChatMessage,
  type ChatReport,
  type CreateProjectInput,
  type ExperimentDataSourceConfig,
  type ExperimentSpec,
  type ExperimentSpecsByName,
  type HypothesisValidatorFinalizeInput,
  type LabPanelView,
  type MatchViewContextValue,
  type ModuleFormValuesByExperiment,
  type ModuleId,
  type ModuleRunChatMessage,
  type ModuleRunRecord,
  type ModuleRunsByExperiment,
  type NewExperimentInput,
  type Persona,
  type Phase,
  type Project,
  type Tab,
  type TextChatMessage,
  type BriefHandoffChatMessage,
  type ThreadGroup,
  type WorkflowProgressByExperiment,
  isModuleRunMessage,
} from './types'

const MatchViewContext = createContext<MatchViewContextValue | null>(null)

let messageCounter = 100

function nextMessageId() {
  messageCounter += 1
  return `m${messageCounter}`
}

function nextThreadId() {
  return `t-${Date.now()}`
}

export function MatchViewProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [currentPersona, setCurrentPersona] = useState<Persona>('executive')
  const [currentTab, setCurrentTab] = useState<Tab>('chat')
  const [experiments, setExperiments] = useState<string[]>([...INITIAL_EXPERIMENTS])
  const [threadGroups, setThreadGroups] = useState<ThreadGroup[]>(
    structuredClone(INITIAL_THREAD_GROUPS),
  )
  const [activeThreadId, setActiveThreadId] = useState(INITIAL_ACTIVE_THREAD_ID)
  const [messagesByThread, setMessagesByThread] = useState<Record<string, ChatMessage[]>>(
    buildInitialMessages,
  )
  const [selectedExperiment, setSelectedExperimentState] = useState<string>(INITIAL_EXPERIMENTS[0])
  const [activePhase, setActivePhase] = useState<Phase>('auto')
  const [activeModuleId, setActiveModuleId] = useState<ModuleId | null>(null)
  const [chartDrawerOpen, setChartDrawerOpen] = useState(false)
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null)
  const [chartDrawerTargetId, setChartDrawerTargetId] = useState<string | null>(null)
  const [hypothesisValidatorOpen, setHypothesisValidatorOpen] = useState(false)
  const [hypothesisValidatorInitialStep, setHypothesisValidatorInitialStep] = useState<number | null>(null)
  const [audienceWizardOpen, setAudienceWizardOpen] = useState(false)
  const [newProjectPanelOpen, setNewProjectPanelOpen] = useState(false)
  const [knowledgeArchiveOpen, setKnowledgeArchiveOpen] = useState(false)
  const [projects, setProjects] = useState<Project[]>(() => structuredClone(INITIAL_PROJECTS))
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [experimentProjectIds, setExperimentProjectIds] = useState<Record<string, string>>(
    () => ({ ...INITIAL_EXPERIMENT_PROJECT_IDS }),
  )
  const [labPanelView, setLabPanelView] = useState<LabPanelView>('tree')
  const [labModuleId, setLabModuleId] = useState<ModuleId | null>(null)
  const [moduleFormValuesByExperiment, setModuleFormValuesByExperiment] =
    useState<ModuleFormValuesByExperiment>({})
  const [moduleRunsByExperiment, setModuleRunsByExperiment] =
    useState<ModuleRunsByExperiment>(() => structuredClone(INITIAL_MODULE_RUNS))
  const [moduleRunStatus, setModuleRunStatus] = useState<
    'idle' | 'running' | 'success' | 'error'
  >('idle')
  const [analyticsLabCollapsed, setAnalyticsLabCollapsed] = useState(false)
  const [analyticsLabExpanded, setAnalyticsLabExpanded] = useState(false)
  const [highlightedFieldKeys, setHighlightedFieldKeys] = useState<string[]>([])
  const [chatReports, setChatReports] = useState<ChatReport[]>(() => buildInitialReports())
  const [experimentDataSourcesDialogExperiment, setExperimentDataSourcesDialogExperiment] =
    useState<string | null>(null)
  const [experimentDataSources, setExperimentDataSources] = useState<
    Record<string, ExperimentDataSourceConfig>
  >(() =>
    Object.fromEntries(
      INITIAL_EXPERIMENTS.map((name) => [name, { type: 'internal' as const }]),
    ),
  )
  const [experimentSpecsByName, setExperimentSpecsByName] = useState<ExperimentSpecsByName>({})
  const [workflowProgressByExperiment, setWorkflowProgressByExperiment] =
    useState<WorkflowProgressByExperiment>({})
  const [pendingModuleActivation, setPendingModuleActivation] = useState<ModuleId | null>(null)
  const [isLlmProcessing, setIsLlmProcessing] = useState(false)

  const runTimeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const highlightTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const tickerMetrics = useMemo(
    () => buildWorkspaceStats(computeLiveExperimentStats(experiments, workflowProgressByExperiment)),
    [experiments, workflowProgressByExperiment],
  )

  const login = useCallback((email: string, _password: string) => {
    const trimmed = email.trim()
    if (!trimmed) return false
    setCurrentUser({
      name: 'Sashikiran',
      email: trimmed,
      avatarUrl: 'https://api.dicebear.com/7.x/personas/svg?seed=Sashikiran&backgroundColor=132744',
    })
    setIsAuthenticated(true)
    return true
  }, [])

  const logout = useCallback(() => {
    setIsAuthenticated(false)
    setCurrentUser(null)
  }, [])

  const clearRunTimeouts = useCallback(() => {
    runTimeoutsRef.current.forEach(clearTimeout)
    runTimeoutsRef.current = []
  }, [])

  const setPersona = useCallback(
    (persona: Persona) => {
      setCurrentPersona(persona)
      if (persona === 'executive') {
        setActiveModuleId(null)
        setLabModuleId(null)
        setLabPanelView('tree')
        setModuleRunStatus('idle')
        clearRunTimeouts()
        setActivePhase((prev) =>
          ANALYST_SUB_PHASES.includes(prev) ? 'auto' : prev,
        )
      }
    },
    [clearRunTimeouts],
  )

  const setTab = useCallback((tab: Tab) => {
    setCurrentTab(tab)
  }, [])

  const selectThread = useCallback((threadId: string, experiment: string) => {
    setActiveThreadId(threadId)
    setSelectedExperimentState(experiment)
    setCurrentTab('chat')
    setActiveModuleId(null)
    setLabModuleId(null)
    setLabPanelView('tree')
    setModuleRunStatus('idle')
    clearRunTimeouts()
  }, [clearRunTimeouts])

  const selectModule = useCallback((moduleId: ModuleId) => {
    setActiveModuleId(moduleId)
    setActivePhase(moduleId)
    setCurrentTab('chat')
  }, [])

  const clearActiveModule = useCallback(() => setActiveModuleId(null), [])

  const applyLabModuleSelection = useCallback(
    (moduleId: ModuleId, experimentOverride?: string) => {
      const experiment = experimentOverride ?? selectedExperiment
      setLabModuleId(moduleId)
      setLabPanelView('form')
      setActiveModuleId(moduleId)
      setActivePhase(moduleId)
      setModuleFormValuesByExperiment((prev) => {
        const experimentValues = prev[experiment] ?? {}
        const schema = getModuleFormSchema(moduleId, experiment)
        let defaults = getDefaultFormValues(schema)
        const spec = experimentSpecsByName[experiment]
        const existing = experimentValues[moduleId]

        if (moduleId === 'metrics-tracking' && spec && !existing) {
          const sizing = experimentValues['opportunity-sizing']
          const expectedLift =
            typeof sizing?.expectedLift === 'number' ? sizing.expectedLift : undefined
          defaults = {
            ...defaults,
            ...buildMetricsFormDefaults(spec.hypothesis, spec.goal, expectedLift),
          }
        }

        if (moduleId === 'experiment-type' && spec && !existing) {
          const sizing = experimentValues['opportunity-sizing']
          const expectedLift =
            typeof sizing?.expectedLift === 'number' ? sizing.expectedLift : undefined
          defaults = {
            ...defaults,
            ...buildExperimentTypeDefaults(spec.hypothesis, spec.goal, expectedLift),
          }
        }

        if (moduleId === 'brief-generator' && spec) {
          defaults = {
            ...(existing ?? defaults),
            briefTitle: `${spec.name} — Digital Experiment Brief`,
            briefBody: buildBriefBody(spec, {
              ...experimentValues,
              ...(existing ? { 'brief-generator': existing } : {}),
            }),
          }
          return {
            ...prev,
            [experiment]: {
              ...experimentValues,
              [moduleId]: defaults,
            },
          }
        }

        if (existing) return prev

        return {
          ...prev,
          [experiment]: {
            ...experimentValues,
            [moduleId]: defaults,
          },
        }
      })
    },
    [selectedExperiment, experimentSpecsByName],
  )

  const selectLabModule = useCallback(
    (moduleId: ModuleId) => {
      setAnalyticsLabCollapsed(false)
      applyLabModuleSelection(moduleId)
    },
    [applyLabModuleSelection],
  )

  const clearPendingModuleActivation = useCallback(() => {
    setPendingModuleActivation(null)
  }, [])

  const updateExperimentSpec = useCallback((experiment: string, patch: Partial<ExperimentSpec>) => {
    setExperimentSpecsByName((prev) => {
      const existing = prev[experiment]
      if (!existing) return prev
      return { ...prev, [experiment]: { ...existing, ...patch } }
    })
  }, [])

  const markWorkflowStepComplete = useCallback((experiment: string, stepId: WorkflowStepId) => {
    setWorkflowProgressByExperiment((prev) => ({
      ...prev,
      [experiment]: markStepComplete(prev[experiment] ?? {}, stepId),
    }))
  }, [])

  const advanceToWorkflowStep = useCallback(
    (moduleId: ModuleId) => {
      setAnalyticsLabCollapsed(false)
      setCurrentPersona('analyst')
      applyLabModuleSelection(moduleId)
      setPendingModuleActivation(moduleId)
    },
    [applyLabModuleSelection],
  )

  const flashHighlightedFields = useCallback((keys: string[]) => {
    if (highlightTimeoutRef.current) clearTimeout(highlightTimeoutRef.current)
    setHighlightedFieldKeys(keys)
    highlightTimeoutRef.current = setTimeout(() => {
      setHighlightedFieldKeys([])
      highlightTimeoutRef.current = null
    }, 500)
  }, [])

  const completeWorkflowStep = useCallback(
    (moduleId: ModuleId, experiment?: string) => {
      if (!isWorkflowStepId(moduleId)) return
      const experimentKey = experiment ?? selectedExperiment
      setWorkflowProgressByExperiment((prev) => ({
        ...prev,
        [experimentKey]: markStepComplete(prev[experimentKey] ?? {}, moduleId),
      }))
    },
    [selectedExperiment],
  )

  const injectNlpParameters = useCallback(
    (moduleId: ModuleId, params: Record<string, unknown>, touchedFields: string[]) => {
      setAnalyticsLabCollapsed(false)
      applyLabModuleSelection(moduleId)
      setModuleFormValuesByExperiment((prev) => ({
        ...prev,
        [selectedExperiment]: {
          ...(prev[selectedExperiment] ?? {}),
          [moduleId]: {
            ...(prev[selectedExperiment]?.[moduleId] ?? {}),
            ...params,
          },
        },
      }))
      flashHighlightedFields(touchedFields)
    },
    [applyLabModuleSelection, selectedExperiment, flashHighlightedFields],
  )

  const getLockedModuleSnapshot = useCallback(
    (moduleId: ModuleId) => {
      const base =
        moduleFormValuesByExperiment[selectedExperiment]?.[moduleId] ??
        getDefaultFormValues(getModuleFormSchema(moduleId, selectedExperiment))
      return structuredClone(base)
    },
    [moduleFormValuesByExperiment, selectedExperiment],
  )

  const updateModuleFormField = useCallback(
    (moduleId: ModuleId, key: string, value: unknown) => {
      setModuleFormValuesByExperiment((prev) => ({
        ...prev,
        [selectedExperiment]: {
          ...(prev[selectedExperiment] ?? {}),
          [moduleId]: {
            ...(prev[selectedExperiment]?.[moduleId] ?? {}),
            [key]: value,
          },
        },
      }))
    },
    [selectedExperiment],
  )

  const resetLabToTree = useCallback(() => {
    setLabPanelView('tree')
    setLabModuleId(null)
  }, [])

  const toggleAnalyticsLabCollapsed = useCallback(() => {
    setAnalyticsLabCollapsed((prev) => !prev)
  }, [])

  const toggleAnalyticsLabExpanded = useCallback(() => {
    setAnalyticsLabExpanded((prev) => !prev)
  }, [])

  const setLabPanelViewState = useCallback((view: LabPanelView) => {
    setLabPanelView(view)
    if (view === 'tree') setLabModuleId(null)
  }, [])

  const scrollToMessage = useCallback((messageId: string) => {
    setHighlightedMessageId(messageId)
    setCurrentTab('chat')
  }, [])

  const openModuleRun = useCallback(
    (runId: string) => {
      const runs = moduleRunsByExperiment[selectedExperiment] ?? []
      const run = runs.find((r) => r.id === runId)
      if (!run) return

      setModuleFormValuesByExperiment((prev) => ({
        ...prev,
        [selectedExperiment]: {
          ...(prev[selectedExperiment] ?? {}),
          [run.moduleId]: run.params,
        },
      }))
      setActiveModuleId(run.moduleId)
      setActivePhase(run.moduleId)
      setLabModuleId(run.moduleId)
      setLabPanelView('form')
      setCurrentTab('chat')

      const threadMessages = messagesByThread[activeThreadId] ?? []
      const runMessage = threadMessages.find(
        (m) => isModuleRunMessage(m) && m.runId === runId,
      )
      if (runMessage) {
        scrollToMessage(runMessage.id)
      }
    },
    [moduleRunsByExperiment, selectedExperiment, messagesByThread, activeThreadId, scrollToMessage],
  )

  const runModule = useCallback(
    (moduleId: ModuleId, options?: { skipUserMessage?: boolean; userLabel?: string; paramOverrides?: Record<string, unknown> }) => {
      if (moduleRunStatus === 'running' || !activeThreadId) return

      clearRunTimeouts()
      const params = {
        ...getLockedModuleSnapshot(moduleId),
        ...(options?.paramOverrides ?? {}),
      }
      const steps = buildExecutionLogStream(moduleId, params, selectedExperiment)
      const mod = MODULE_BY_ID[moduleId]
      const now = formatMessageTime()
      const runId = `run-${Date.now()}`
      const runMessageId = nextMessageId()
      const threadId = activeThreadId

      const userMessage: TextChatMessage | null = options?.skipUserMessage
        ? null
        : {
            kind: 'text',
            id: nextMessageId(),
            role: 'user',
            content:
              options?.userLabel ??
              `Run ${mod.label} on ${selectedExperiment}`,
            timestamp: now,
          }

      const runMessage: ModuleRunChatMessage = {
        kind: 'module-run',
        id: runMessageId,
        role: 'assistant',
        content: `Running ${mod.label}…`,
        timestamp: now,
        moduleId,
        runId,
        status: 'running',
        logs: [],
        params,
      }

      setModuleRunStatus('running')
      setCurrentTab('chat')
      applyLabModuleSelection(moduleId)
      setMessagesByThread((prev) => {
        const existing = prev[threadId] ?? []
        const nextMessages = userMessage
          ? [...existing, userMessage, runMessage]
          : [...existing, runMessage]
        return { ...prev, [threadId]: nextMessages }
      })
      setHighlightedMessageId(runMessageId)

      steps.forEach((step) => {
        const timeout = setTimeout(() => {
          setMessagesByThread((prev) => {
            const msgs = prev[threadId] ?? []
            return {
              ...prev,
              [threadId]: msgs.map((m) =>
                m.id === runMessageId && isModuleRunMessage(m)
                  ? { ...m, logs: [...m.logs, step.line] }
                  : m,
              ),
            }
          })
        }, step.delayMs)
        runTimeoutsRef.current.push(timeout)
      })

      const completeTimeout = setTimeout(() => {
        const record: ModuleRunRecord = {
          id: runId,
          moduleId,
          experiment: selectedExperiment,
          params,
          completedAt: formatMessageTime(),
          duration: mod.mockDuration,
          status: 'success',
        }

        setModuleFormValuesByExperiment((prev) => ({
          ...prev,
          [selectedExperiment]: {
            ...(prev[selectedExperiment] ?? {}),
            [moduleId]: params,
          },
        }))

        setModuleRunsByExperiment((prev) => ({
          ...prev,
          [selectedExperiment]: [record, ...(prev[selectedExperiment] ?? [])].slice(0, 20),
        }))

        setActiveModuleId(moduleId)
        setActivePhase(moduleId)
        setModuleRunStatus('success')

        const evaluation = buildModuleEvaluation(moduleId, params)

        if (isWorkflowStepId(moduleId)) {
          const canComplete =
            moduleId !== 'metrics-tracking' ||
            Boolean(String(params.featureDescription ?? '').trim())
          if (canComplete) {
            setWorkflowProgressByExperiment((prev) => ({
              ...prev,
              [selectedExperiment]: markStepComplete(prev[selectedExperiment] ?? {}, moduleId),
            }))
          }
        }

        if (moduleId === 'metrics-tracking') {
          setExperimentSpecsByName((prev) => {
            const existing = prev[selectedExperiment]
            if (!existing) return prev
            return {
              ...prev,
              [selectedExperiment]: {
                ...existing,
                metricsApproved: Boolean(String(params.featureDescription ?? '').trim()),
              },
            }
          })
        }

        if (moduleId === 'experiment-type') {
          setExperimentSpecsByName((prev) => {
            const existing = prev[selectedExperiment]
            if (!existing) return prev
            return {
              ...prev,
              [selectedExperiment]: {
                ...existing,
                experimentType: (params.experimentType as ExperimentSpec['experimentType']) ?? 'A/B',
                typeRationale: String(params.typeRationale ?? ''),
              },
            }
          })
        }

        const report: ChatReport = {
          id: `report-${runId}`,
          runId,
          threadId,
          experiment: selectedExperiment,
          moduleId,
          title: `${mod.label} Report`,
          summary: evaluation.summary,
          evaluation,
          completedAt: formatMessageTime(),
          duration: mod.mockDuration,
        }

        setChatReports((prev) => [report, ...prev])

        setMessagesByThread((prev) => {
          const msgs = prev[threadId] ?? []
          return {
            ...prev,
            [threadId]: msgs.map((m) =>
              m.id === runMessageId && isModuleRunMessage(m)
                ? {
                    ...m,
                    status: 'success' as const,
                    duration: mod.mockDuration,
                    evaluation,
                    content: evaluation.summary,
                  }
                : m,
            ),
          }
        })
      }, steps[steps.length - 1].delayMs + 200)
      runTimeoutsRef.current.push(completeTimeout)
    },
    [
      moduleRunStatus,
      activeThreadId,
      selectedExperiment,
      clearRunTimeouts,
      applyLabModuleSelection,
      getLockedModuleSnapshot,
    ],
  )

  const runActiveLabModule = useCallback(() => {
    if (!labModuleId || moduleRunStatus === 'running') return
    runModule(labModuleId)
  }, [labModuleId, moduleRunStatus, runModule])

  const processChatInput = useCallback(
    (content: string) => {
      const trimmed = content.trim()
      if (!trimmed || !activeThreadId) return

      const now = formatMessageTime()
      const messages = messagesByThread[activeThreadId] ?? []
      const intent = resolveChatIntent(trimmed, {
        persona: currentPersona,
        activeModuleId,
        labModuleId,
        selectedExperiment,
        moduleFormValuesByExperiment,
        messages,
      })

      const userMessage: TextChatMessage = {
        kind: 'text',
        id: nextMessageId(),
        role: 'user',
        content: trimmed,
        timestamp: now,
      }

      const appendMessages = (extra: ChatMessage[]) => {
        setMessagesByThread((prev) => ({
          ...prev,
          [activeThreadId]: [...(prev[activeThreadId] ?? []), userMessage, ...extra],
        }))
      }

      const updateMessageContent = (messageId: string, content: string) => {
        setMessagesByThread((prev) => ({
          ...prev,
          [activeThreadId]: (prev[activeThreadId] ?? []).map((m) =>
            m.kind === 'text' && m.id === messageId ? { ...m, content } : m,
          ),
        }))
      }

      /** Intelligent agent chat — sends user messages to Databricks FMAPI with
       * tool definitions for Causal & ROI modules. When the LLM returns tool_calls,
       * the app intercepts them, shows an execution status message, and triggers
       * the corresponding module run programmatically. */
      const appendLlmReply = (userContent: string) => {
        const placeholderId = nextMessageId()
        appendMessages([
          { kind: 'text', id: placeholderId, role: 'assistant', content: 'Thinking…', timestamp: now },
        ])
        setIsLlmProcessing(true)

        const recentHistory: FmapiChatMessage[] = messages
          .filter((m): m is TextChatMessage => m.kind === 'text')
          .slice(-8)
          .map((m) => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))

        const systemPrompt =
          `You are the intelligent agent embedded in MatchView, a physical-store experimentation and causal inference platform. ` +
          `You help analysts design, execute, and interpret store-level experiments.\n\n` +
          `## IMPORTANT: You have tool-calling capabilities.\n` +
          `When the user wants to run an analytical module, USE the provided tools instead of responding with text.\n` +
          `Only respond with plain text when answering informational questions that don't require module execution.\n\n` +
          `## Current Context\n` +
          `- Persona: ${currentPersona}\n` +
          `- Active module: ${labModuleId ?? activeModuleId ?? 'none'}\n` +
          `- Experiment: ${selectedExperiment || 'none'}\n\n` +
          `## Data Schema\n` +
          `- store_master: 9,500 stores (store_id, region, state, format_type, risk_tier, store_size_sqft)\n` +
          `- store_performance_weekly: KPIs (total_sales, traffic, conversion_rate, upt, aur, gold_score) by store+week\n` +
          `- initiative_catalog: 25 initiatives (initiative_id, name, category, expected_lag_weeks)\n` +
          `- store_initiative_mapping: Concurrency (rollout_date, status, cohort_label)\n` +
          `- macro_external_data: Externals (weather_index, economic_index, holiday_flag, competitor_event) by zip+week\n\n` +
          `## Guidelines\n` +
          `1. When the user asks to run forecasting, causal inference, ROI analysis, learnings lookup, or heterogeneity checks — call the appropriate tool.\n` +
          `2. Extract parameters from natural language (e.g. "4 weeks" → weeks_of_flight: 4, "use prophet" → model: "prophet").\n` +
          `3. For informational questions ("what is DiD?", "explain the results"), respond with concise markdown text (2-4 sentences).\n` +
          `4. If unsure which tool to use, ask a clarifying question.`

        queryFmapiChat(
          [...recentHistory, { role: 'user', content: userContent }],
          { systemPrompt, maxTokens: 1024, tools: AGENT_TOOLS, tool_choice: 'auto' },
        ).then(
          (result) => {
            setIsLlmProcessing(false)

            // ── Handle tool_calls response (agent wants to execute a module) ──
            if (result.tool_calls && result.tool_calls.length > 0) {
              const toolCall: FmapiToolCall = result.tool_calls[0]
              const toolName = toolCall.function.name
              let toolArgs: Record<string, unknown> = {}
              try {
                toolArgs = JSON.parse(toolCall.function.arguments)
              } catch { /* empty args fallback */ }

              const mapping = getModuleForTool(toolName)
              if (mapping) {
                // Show execution status message in the chat
                const summary = buildToolCallSummary(toolName, toolArgs)
                updateMessageContent(placeholderId, summary)

                // Convert tool args to module form params and inject into Analytics Lab
                const moduleParams = toolArgsToModuleParams(toolName, toolArgs)
                injectNlpParameters(mapping.moduleId, moduleParams, Object.keys(moduleParams))

                // Trigger the module execution after a short delay for state propagation
                setTimeout(() => {
                  runModule(mapping.moduleId, { skipUserMessage: true, paramOverrides: moduleParams })
                }, 200)
              } else {
                updateMessageContent(placeholderId, `Attempted to call unknown tool: ${toolName}`)
              }
              return
            }

            // ── Handle plain text response (informational answer) ──
            if (result.reply) {
              updateMessageContent(placeholderId, result.reply)
            } else {
              updateMessageContent(
                placeholderId,
                buildAssistantReply(currentPersona, userContent) +
                  (result.error ? `\n\n(Model endpoint unavailable: ${result.error})` : ''),
              )
            }
          },
        ).catch(() => {
          setIsLlmProcessing(false)
          updateMessageContent(placeholderId, 'An error occurred while processing your request.')
        })
      }

      if (currentPersona === 'executive' || intent.type === 'text-reply') {
        if (intent.type === 'text-reply') {
          // Analysts get LLM responses; executives get canned replies
          if (currentPersona === 'analyst') {
            appendLlmReply(trimmed)
          } else {
            appendMessages([
              { kind: 'text', id: nextMessageId(), role: 'assistant', content: intent.reply, timestamp: now },
            ])
          }
        } else {
          // Executive persona with non-text-reply intents → LLM
          appendLlmReply(trimmed)
        }
        return
      }

      switch (intent.type) {
        case 'module-suggest':
          // Navigate to module AND get LLM intelligence for model recommendations
          if ('moduleId' in intent) {
            applyLabModuleSelection(intent.moduleId as ModuleId)
            setAnalyticsLabCollapsed(false)
          }
          // Route through LLM for structured param extraction + model recommendation
          appendLlmReply(trimmed)
          break
        case 'llm-route':
          // Explicit LLM fallback from intent router
          appendLlmReply(trimmed)
          break
        case 'contextual-run':
          appendMessages([
            {
              kind: 'text',
              id: nextMessageId(),
              role: 'assistant',
              content: intent.reply,
              timestamp: now,
            },
          ])
          break
        case 'advance-workflow':
          appendMessages([
            {
              kind: 'text',
              id: nextMessageId(),
              role: 'assistant',
              content: intent.reply,
              timestamp: now,
            },
          ])
          advanceToWorkflowStep(intent.moduleId)
          break
        case 'open-insights':
          setCurrentTab('insights')
          appendMessages([
            {
              kind: 'text',
              id: nextMessageId(),
              role: 'assistant',
              content: intent.reply,
              timestamp: now,
            },
          ])
          break
        case 'nlp-inject': {
          injectNlpParameters(intent.moduleId, intent.params, intent.touchedFields)
          // Detect if user implies execution ("give", "show", "run", "generate", "predict")
          const wantsRun = /\b(give|show|run|generate|predict|execute|compute|start|do)\b/i.test(intent.userContent)
          if (wantsRun) {
            appendMessages([
              {
                kind: 'text',
                id: nextMessageId(),
                role: 'assistant',
                content: `Running **${MODULE_BY_ID[intent.moduleId].label}** with your parameters (${intent.touchedFields.join(', ')})…`,
                timestamp: now,
              },
            ])
            setTimeout(() => {
              runModule(intent.moduleId, { skipUserMessage: true, paramOverrides: intent.params })
            }, 100)
          } else {
            appendMessages([
              {
                kind: 'text',
                id: nextMessageId(),
                role: 'assistant',
                content: intent.reply,
                timestamp: now,
              },
            ])
          }
          break
        }
        default:
          appendLlmReply(trimmed)
      }
    },
    [
      activeThreadId,
      messagesByThread,
      currentPersona,
      activeModuleId,
      labModuleId,
      selectedExperiment,
      moduleFormValuesByExperiment,
      injectNlpParameters,
      advanceToWorkflowStep,
      applyLabModuleSelection,
    ],
  )

  const appendChatMessages = useCallback(
    (messages: TextChatMessage[]) => {
      if (!activeThreadId || messages.length === 0) return
      setMessagesByThread((prev) => ({
        ...prev,
        [activeThreadId]: [...(prev[activeThreadId] ?? []), ...messages],
      }))
    },
    [activeThreadId],
  )

  const sendMessage = useCallback(
    (content: string) => {
      processChatInput(content)
    },
    [processChatInput],
  )

  const executePill = useCallback(
    (prompt: string) => {
      processChatInput(prompt)
    },
    [processChatInput],
  )

  const openChartDrawer = useCallback((chartId: string) => {
    setChartDrawerTargetId(chartId)
    setChartDrawerOpen(true)
  }, [])

  const closeChartDrawer = useCallback(() => {
    setChartDrawerOpen(false)
    setChartDrawerTargetId(null)
  }, [])

  const openHypothesisValidator = useCallback(() => {
    setHypothesisValidatorInitialStep(null)
    setHypothesisValidatorOpen(true)
  }, [])

  const openHypothesisValidatorAtStep = useCallback((step: number) => {
    setHypothesisValidatorInitialStep(step)
    setHypothesisValidatorOpen(true)
  }, [])

  const closeHypothesisValidator = useCallback(() => {
    setHypothesisValidatorOpen(false)
    setHypothesisValidatorInitialStep(null)
  }, [])

  const openAudienceWizard = useCallback(() => setAudienceWizardOpen(true), [])

  const closeAudienceWizard = useCallback(() => setAudienceWizardOpen(false), [])

  const saveAudienceSelection = useCallback(
    (values: { segment: string; trafficPercent: number; exclusions: string }) => {
      if (!selectedExperiment) return
      setModuleFormValuesByExperiment((prev) => ({
        ...prev,
        [selectedExperiment]: {
          ...(prev[selectedExperiment] ?? {}),
          'audience-selection': { ...values },
        },
      }))
      setWorkflowProgressByExperiment((prev) => ({
        ...prev,
        [selectedExperiment]: {
          ...(prev[selectedExperiment] ?? {}),
          'audience-selection': true,
        },
      }))
      setAudienceWizardOpen(false)
    },
    [selectedExperiment],
  )

  const openNewProjectPanel = useCallback(() => setNewProjectPanelOpen(true), [])

  const closeNewProjectPanel = useCallback(() => setNewProjectPanelOpen(false), [])

  const openKnowledgeArchive = useCallback(() => setKnowledgeArchiveOpen(true), [])

  const closeKnowledgeArchive = useCallback(() => setKnowledgeArchiveOpen(false), [])

  const goHome = useCallback(() => {
    setSelectedProjectId(null)
    setNewProjectPanelOpen(false)
    setHypothesisValidatorOpen(false)
    setAudienceWizardOpen(false)
    setActiveModuleId(null)
    setLabModuleId(null)
    setLabPanelView('tree')
  }, [])

  const selectProject = useCallback(
    (projectId: string) => {
      const project = projects.find((p) => p.id === projectId)
      if (!project) return

      setSelectedProjectId(projectId)
      setHypothesisValidatorOpen(false)
      setAudienceWizardOpen(false)
      setNewProjectPanelOpen(false)

      const projectGroups = threadGroups.filter((g) => g.projectId === projectId)
      const firstGroup = projectGroups[0]
      const firstThread = firstGroup?.threads[0]
      if (firstThread && firstGroup) {
        setActiveThreadId(firstThread.id)
        setSelectedExperimentState(firstGroup.experiment)
      } else {
        const expName =
          Object.entries(experimentProjectIds).find(([, pid]) => pid === projectId)?.[0] ??
          experiments.find((e) => experimentProjectIds[e] === projectId) ??
          ''
        if (expName) setSelectedExperimentState(expName)
        setActiveThreadId('')
      }
      setCurrentTab('chat')
      setActiveModuleId(null)
      setLabModuleId(null)
      setLabPanelView('tree')
    },
    [projects, threadGroups, experimentProjectIds, experiments],
  )

  const createProject = useCallback((input: CreateProjectInput) => {
    const name = input.name.trim()
    if (!name) return

    const id = `proj-${Date.now()}`
    const project: Project = {
      id,
      name,
      description: input.description.trim(),
      objective: input.objective?.trim() || undefined,
      channel: input.channel,
      dataSource: input.dataSource,
      createdAt: new Date().toISOString().slice(0, 10),
    }

    setProjects((prev) => [project, ...prev])
    setSelectedProjectId(id)
    setActiveThreadId('')
    setSelectedExperimentState('')
    setCurrentTab('chat')
    setNewProjectPanelOpen(false)
    setActiveModuleId(null)
    setLabModuleId(null)
    setLabPanelView('tree')
  }, [])

  const deleteProject = useCallback(
    (projectId: string) => {
      const expNames = Object.entries(experimentProjectIds)
        .filter(([, pid]) => pid === projectId)
        .map(([name]) => name)

      setProjects((prev) => prev.filter((p) => p.id !== projectId))
      setExperimentProjectIds((prev) => {
        const next = { ...prev }
        expNames.forEach((n) => delete next[n])
        return next
      })
      setExperiments((prev) => prev.filter((e) => !expNames.includes(e)))
      setThreadGroups((prev) => prev.filter((g) => g.projectId !== projectId))
      setMessagesByThread((prev) => {
        const removeIds = new Set(
          threadGroups
            .filter((g) => g.projectId === projectId)
            .flatMap((g) => g.threads.map((t) => t.id)),
        )
        const next = { ...prev }
        removeIds.forEach((id) => delete next[id])
        return next
      })
      setChatReports((prev) => prev.filter((r) => !expNames.includes(r.experiment)))
      setExperimentDataSources((prev) => {
        const next = { ...prev }
        expNames.forEach((n) => delete next[n])
        return next
      })
      setExperimentSpecsByName((prev) => {
        const next = { ...prev }
        expNames.forEach((n) => delete next[n])
        return next
      })
      setWorkflowProgressByExperiment((prev) => {
        const next = { ...prev }
        expNames.forEach((n) => delete next[n])
        return next
      })
      setModuleFormValuesByExperiment((prev) => {
        const next = { ...prev }
        expNames.forEach((n) => delete next[n])
        return next
      })
      setModuleRunsByExperiment((prev) => {
        const next = { ...prev }
        expNames.forEach((n) => delete next[n])
        return next
      })

      if (selectedProjectId === projectId) {
        setSelectedProjectId(null)
        setActiveThreadId('')
        setSelectedExperimentState('')
      }
    },
    [experimentProjectIds, threadGroups, selectedProjectId],
  )

  const openExperimentDataSources = useCallback((experiment: string) => {
    setExperimentDataSourcesDialogExperiment(experiment)
  }, [])

  const closeExperimentDataSourcesDialog = useCallback(() => {
    setExperimentDataSourcesDialogExperiment(null)
  }, [])

  const updateExperimentDataSources = useCallback(
    (experiment: string, config: ExperimentDataSourceConfig) => {
      setExperimentDataSources((prev) => ({ ...prev, [experiment]: config }))
      setExperimentDataSourcesDialogExperiment(null)
    },
    [],
  )

  const deleteThread = useCallback(
    (threadId: string, experiment: string) => {
      const nextGroups = threadGroups
        .map((g) =>
          g.experiment === experiment
            ? { ...g, threads: g.threads.filter((t) => t.id !== threadId) }
            : g,
        )
        .filter((g) => g.threads.length > 0)

      setThreadGroups(nextGroups)
      setMessagesByThread((prev) => {
        const { [threadId]: _removed, ...rest } = prev
        return rest
      })

      if (activeThreadId === threadId) {
        const fallbackGroup =
          nextGroups.find((g) => g.experiment === experiment) ?? nextGroups[0]
        const fallback = fallbackGroup?.threads[0]
        if (fallback) {
          setActiveThreadId(fallback.id)
          setSelectedExperimentState(fallbackGroup.experiment)
        }
      }
    },
    [threadGroups, activeThreadId],
  )

  const deleteExperiment = useCallback(
    (experiment: string) => {
      const group = threadGroups.find((g) => g.experiment === experiment)
      if (!group) return

      const threadIds = new Set(group.threads.map((t) => t.id))
      const remainingGroups = threadGroups.filter((g) => g.experiment !== experiment)

      setThreadGroups(remainingGroups)
      setExperiments((prev) => prev.filter((e) => e !== experiment))
      setExperimentProjectIds((prev) => {
        const { [experiment]: _removed, ...rest } = prev
        return rest
      })
      setMessagesByThread((prev) => {
        const next = { ...prev }
        threadIds.forEach((id) => delete next[id])
        return next
      })
      setExperimentDataSources((prev) => {
        const { [experiment]: _removed, ...rest } = prev
        return rest
      })
      setExperimentSpecsByName((prev) => {
        const { [experiment]: _removed, ...rest } = prev
        return rest
      })
      setWorkflowProgressByExperiment((prev) => {
        const { [experiment]: _removed, ...rest } = prev
        return rest
      })
      setExperimentDataSourcesDialogExperiment(null)

      if (threadIds.has(activeThreadId)) {
        const fallbackGroup = remainingGroups[0]
        const fallbackThread = fallbackGroup?.threads[0]
        if (fallbackThread) {
          setActiveThreadId(fallbackThread.id)
          setSelectedExperimentState(fallbackGroup.experiment)
        }
      } else if (selectedExperiment === experiment && remainingGroups[0]) {
        setSelectedExperimentState(remainingGroups[0].experiment)
      }
    },
    [threadGroups, activeThreadId, selectedExperiment],
  )

  const createExperiment = useCallback(
    (input: NewExperimentInput) => {
      const name = input.name.trim()
      const hypothesis = input.hypothesis.trim()
      const goal = input.goal.trim()
      if (!name || !hypothesis || !goal || !selectedProjectId) return

      const threadId = nextThreadId()
      const now = formatMessageTime()
      const welcome: ChatMessage = {
        id: nextMessageId(),
        role: 'assistant',
        content: buildWelcomeMessage(currentPersona, name, hypothesis, goal),
        timestamp: now,
      }

      const similar = findSimilarLearnings(hypothesis, goal, 3)
      const learningsMessage: ChatMessage = {
        id: nextMessageId(),
        role: 'assistant',
        content: buildSimilarLearningsMessage(similar),
        timestamp: now,
      }

      setExperiments((prev) => (prev.includes(name) ? prev : [...prev, name]))
      setExperimentProjectIds((prev) => ({ ...prev, [name]: selectedProjectId }))
      setExperimentSpecsByName((prev) => ({
        ...prev,
        [name]: { name, hypothesis, goal, channel: 'digital' },
      }))
      setWorkflowProgressByExperiment((prev) => ({
        ...prev,
        [name]: prev[name] ?? {},
      }))
      setThreadGroups((prev) => {
        const existing = prev.find((g) => g.experiment === name)
        const newThread = { id: threadId, title: 'Hypothesis validation', timestamp: 'Just now' }
        if (existing) {
          return prev.map((g) =>
            g.experiment === name ? { ...g, threads: [newThread, ...g.threads] } : g,
          )
        }
        return [
          { projectId: selectedProjectId, experiment: name, threads: [newThread] },
          ...prev,
        ]
      })
      setMessagesByThread((prev) => ({ ...prev, [threadId]: [welcome, learningsMessage] }))
      const project = projects.find((p) => p.id === selectedProjectId)
      setExperimentDataSources((prev) => ({
        ...prev,
        [name]: prev[name] ?? project?.dataSource ?? { type: 'internal' },
      }))
      setActiveThreadId(threadId)
      setSelectedExperimentState(name)
      setCurrentPersona('analyst')
      setCurrentTab('chat')
      setHypothesisValidatorOpen(false)
    },
    [currentPersona, selectedProjectId, projects],
  )

  const finalizeHypothesisValidator = useCallback(
    (input: HypothesisValidatorFinalizeInput) => {
      const name = input.name.trim()
      const hypothesis = input.hypothesis.trim()
      const goal = input.goal.trim()
      if (!name || !hypothesis || !selectedProjectId) return

      const threadId = nextThreadId()
      const now = formatMessageTime()
      const reportId = `report-brief-${Date.now()}`
      const runId = `run-brief-${Date.now()}`

      const welcome: ChatMessage = {
        id: nextMessageId(),
        role: 'assistant',
        content: buildWelcomeMessage('analyst', name, hypothesis, goal),
        timestamp: now,
      }
      const similar = findSimilarLearnings(hypothesis, goal, 3)
      const learningsMessage: ChatMessage = {
        id: nextMessageId(),
        role: 'assistant',
        content: buildSimilarLearningsMessage(similar),
        timestamp: now,
      }
      const briefMessage: BriefHandoffChatMessage = {
        kind: 'brief-handoff',
        id: nextMessageId(),
        role: 'assistant',
        content: input.briefTitle,
        timestamp: now,
        reportId,
        briefTitle: input.briefTitle,
        briefBody: input.briefBody,
        experimentType: input.experimentTypeChoice,
        typeRationale: input.typeRationale,
      }
      const report: ChatReport = {
        id: reportId,
        runId,
        threadId,
        experiment: name,
        moduleId: 'brief-generator',
        title: input.briefTitle,
        summary: input.briefBody.slice(0, 280) + (input.briefBody.length > 280 ? '…' : ''),
        evaluation: { type: 'generic', summary: input.briefBody },
        completedAt: now,
        duration: '0s',
      }

      setExperiments((prev) => (prev.includes(name) ? prev : [...prev, name]))
      setExperimentProjectIds((prev) => ({ ...prev, [name]: selectedProjectId }))
      setExperimentSpecsByName((prev) => ({
        ...prev,
        [name]: {
          name,
          hypothesis,
          goal,
          channel: 'digital',
          experimentType: input.experimentTypeChoice,
          typeRationale: input.typeRationale,
          funnelStage: input.funnelStage,
          metricsApproved: input.metricsApproved,
        },
      }))
      setWorkflowProgressByExperiment((prev) => ({
        ...prev,
        [name]: {
          'opportunity-sizing': true,
          'metrics-tracking': true,
          'experiment-type': true,
          'power-calculator': true,
          'audience-selection': false,
          'brief-generator': true,
        },
      }))
      setModuleFormValuesByExperiment((prev) => ({
        ...prev,
        [name]: {
          ...(prev[name] ?? {}),
          'opportunity-sizing': input.opportunity,
          'metrics-tracking': input.metrics,
          'experiment-type': input.experimentType,
          'power-calculator': input.power,
          'brief-generator': {
            briefTitle: input.briefTitle,
            briefBody: input.briefBody,
          },
        },
      }))
      setThreadGroups((prev) => {
        const existing = prev.find((g) => g.experiment === name)
        const newThread = { id: threadId, title: 'Experiment brief ready', timestamp: 'Just now' }
        if (existing) {
          return prev.map((g) =>
            g.experiment === name ? { ...g, threads: [newThread, ...g.threads] } : g,
          )
        }
        return [
          { projectId: selectedProjectId, experiment: name, threads: [newThread] },
          ...prev,
        ]
      })
      setMessagesByThread((prev) => ({
        ...prev,
        [threadId]: [welcome, learningsMessage, briefMessage],
      }))
      setChatReports((prev) => [report, ...prev])
      const project = projects.find((p) => p.id === selectedProjectId)
      setExperimentDataSources((prev) => ({
        ...prev,
        [name]: prev[name] ?? project?.dataSource ?? { type: 'internal' },
      }))
      setActiveThreadId(threadId)
      setSelectedExperimentState(name)
      setCurrentPersona('analyst')
      setCurrentTab('chat')
      setActiveModuleId(null)
      setLabModuleId(null)
      setLabPanelView('tree')
      setActivePhase('planning')
      setPendingModuleActivation(null)
      setAnalyticsLabCollapsed(false)
      setHypothesisValidatorOpen(false)
    },
    [selectedProjectId, projects],
  )

  const openReport = useCallback(
    (reportId: string) => {
      const report = chatReports.find((r) => r.id === reportId)
      if (!report) return

      setSelectedExperimentState(report.experiment)
      setActiveThreadId(report.threadId)
      setActiveModuleId(report.moduleId)
      setActivePhase(report.moduleId)
      setCurrentTab(report.moduleId === 'brief-generator' ? 'reports' : 'insights')
    },
    [chatReports],
  )

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeChartDrawer()
        setHypothesisValidatorOpen(false)
        setNewProjectPanelOpen(false)
        setExperimentDataSourcesDialogExperiment(null)
        setHighlightedMessageId(null)
        return
      }
      if (
        (e.metaKey || e.ctrlKey) &&
        e.key === 'Enter' &&
        currentPersona === 'analyst' &&
        labModuleId &&
        moduleRunStatus !== 'running'
      ) {
        e.preventDefault()
        runActiveLabModule()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [closeChartDrawer, currentPersona, labModuleId, moduleRunStatus, runActiveLabModule])

  useEffect(() => {
    if (!highlightedMessageId) return
    const timer = setTimeout(() => setHighlightedMessageId(null), 3000)
    return () => clearTimeout(timer)
  }, [highlightedMessageId])

  useEffect(() => () => clearRunTimeouts(), [clearRunTimeouts])

  const value = useMemo<MatchViewContextValue>(
    () => ({
      isAuthenticated,
      currentUser,
      currentPersona,
      currentTab,
      selectedExperiment,
      activePhase,
      activeModuleId,
      chartDrawerOpen,
      highlightedMessageId,
      chartDrawerTargetId,
      hypothesisValidatorOpen,
      hypothesisValidatorInitialStep,
      audienceWizardOpen,
      newProjectPanelOpen,
      projects,
      selectedProjectId,
      experimentProjectIds,
      experiments,
      threadGroups,
      activeThreadId,
      messagesByThread,
      chatReports,
      tickerMetrics,
      labPanelView,
      labModuleId,
      moduleFormValuesByExperiment,
      moduleRunsByExperiment,
      moduleRunStatus,
      analyticsLabCollapsed,
      analyticsLabExpanded,
      highlightedFieldKeys,
      experimentDataSourcesDialogExperiment,
      experimentDataSources,
      experimentSpecsByName,
      workflowProgressByExperiment,
      pendingModuleActivation,
      isLlmProcessing,
      login,
      logout,
      setPersona,
      setTab,
      setActivePhase,
      openChartDrawer,
      closeChartDrawer,
      goHome,
      selectProject,
      openNewProjectPanel,
      closeNewProjectPanel,
      knowledgeArchiveOpen,
      completeWorkflowStep,
      openKnowledgeArchive,
      closeKnowledgeArchive,
      createProject,
      deleteProject,
      openHypothesisValidator,
      openHypothesisValidatorAtStep,
      closeHypothesisValidator,
      openAudienceWizard,
      closeAudienceWizard,
      saveAudienceSelection,
      createExperiment,
      finalizeHypothesisValidator,
      selectThread,
      deleteThread,
      deleteExperiment,
      openExperimentDataSources,
      closeExperimentDataSourcesDialog,
      updateExperimentDataSources,
      updateExperimentSpec,
      markWorkflowStepComplete,
      clearPendingModuleActivation,
      advanceToWorkflowStep,
      selectModule,
      clearActiveModule,
      sendMessage,
      appendChatMessages,
      executePill,
      scrollToMessage,
      selectLabModule,
      updateModuleFormField,
      injectNlpParameters,
      getLockedModuleSnapshot,
      runActiveLabModule,
      runModule,
      resetLabToTree,
      toggleAnalyticsLabCollapsed,
      toggleAnalyticsLabExpanded,
      openModuleRun,
      setLabPanelView: setLabPanelViewState,
      openReport,
    }),
    [
      isAuthenticated,
      currentUser,
      currentPersona,
      currentTab,
      selectedExperiment,
      activePhase,
      activeModuleId,
      chartDrawerOpen,
      highlightedMessageId,
      chartDrawerTargetId,
      hypothesisValidatorOpen,
      hypothesisValidatorInitialStep,
      audienceWizardOpen,
      newProjectPanelOpen,
      projects,
      selectedProjectId,
      experimentProjectIds,
      experiments,
      threadGroups,
      activeThreadId,
      messagesByThread,
      chatReports,
      tickerMetrics,
      labPanelView,
      labModuleId,
      moduleFormValuesByExperiment,
      moduleRunsByExperiment,
      moduleRunStatus,
      analyticsLabCollapsed,
      analyticsLabExpanded,
      highlightedFieldKeys,
      experimentDataSourcesDialogExperiment,
      experimentDataSources,
      experimentSpecsByName,
      workflowProgressByExperiment,
      pendingModuleActivation,
      login,
      logout,
      setPersona,
      setTab,
      openChartDrawer,
      closeChartDrawer,
      goHome,
      selectProject,
      openNewProjectPanel,
      closeNewProjectPanel,
      knowledgeArchiveOpen,
      openKnowledgeArchive,
      closeKnowledgeArchive,
      completeWorkflowStep,
      createProject,
      deleteProject,
      openHypothesisValidator,
      openHypothesisValidatorAtStep,
      closeHypothesisValidator,
      openAudienceWizard,
      closeAudienceWizard,
      saveAudienceSelection,
      createExperiment,
      finalizeHypothesisValidator,
      selectThread,
      deleteThread,
      deleteExperiment,
      openExperimentDataSources,
      closeExperimentDataSourcesDialog,
      updateExperimentDataSources,
      updateExperimentSpec,
      markWorkflowStepComplete,
      clearPendingModuleActivation,
      advanceToWorkflowStep,
      selectModule,
      clearActiveModule,
      sendMessage,
      appendChatMessages,
      executePill,
      scrollToMessage,
      selectLabModule,
      updateModuleFormField,
      injectNlpParameters,
      getLockedModuleSnapshot,
      runActiveLabModule,
      runModule,
      resetLabToTree,
      toggleAnalyticsLabCollapsed,
      toggleAnalyticsLabExpanded,
      openModuleRun,
      setLabPanelViewState,
      openReport,
    ],
  )

  return <MatchViewContext.Provider value={value}>{children}</MatchViewContext.Provider>
}

export function useMatchView(): MatchViewContextValue {
  const ctx = useContext(MatchViewContext)
  if (!ctx) {
    throw new Error('useMatchView must be used within MatchViewProvider')
  }
  return ctx
}
