import type { WorkflowStepId } from '../data/hypothesisWorkflow'

export type Persona = 'executive' | 'analyst'
export type Tab = 'chat' | 'insights' | 'reports'

export interface AuthUser {
  name: string
  email: string
  avatarUrl: string
}

export type ExecutivePhase = 'auto' | 'discovery' | 'planning' | 'monitoring' | 'analysis'

export type ModuleId =
  | 'data-validation'
  | 'dimension-setup'
  | 'distribution-shift'
  | 'pipeline-health'
  | 'schema-discovery'
  | 'watchtower'
  | 'opportunity-sizing'
  | 'metrics-tracking'
  | 'experiment-type'
  | 'power-calculator'
  | 'audience-selection'
  | 'balance-diagnostics'
  | 'brief-generator'
  | 'experiment-analysis'
  | 'health-monitor'
  | 'sequential-testing'
  | 'causal-did'
  | 'forecasting'
  | 'learnings-repository'
  | 'roi-synthesis'
  | 'simpsons-paradox'

export type ExperimentChannel = 'digital'
export type ExperimentTypeChoice = 'A/B' | 'A/B/C' | 'Causal'

export interface ExperimentSpec {
  name: string
  hypothesis: string
  goal: string
  channel: ExperimentChannel
  experimentType?: ExperimentTypeChoice
  typeRationale?: string
  funnelStage?: string
  metricsApproved?: boolean
}

export type ModulePhaseKey = 'foundation' | 'preplanning' | 'monitoring' | 'causal'

export type Phase = ExecutivePhase | ModuleId | ModulePhaseKey

export const ALL_MODULE_IDS: ModuleId[] = [
  'data-validation',
  'dimension-setup',
  'distribution-shift',
  'pipeline-health',
  'schema-discovery',
  'watchtower',
  'opportunity-sizing',
  'metrics-tracking',
  'experiment-type',
  'power-calculator',
  'audience-selection',
  'balance-diagnostics',
  'brief-generator',
  'experiment-analysis',
  'health-monitor',
  'sequential-testing',
  'causal-did',
  'forecasting',
  'learnings-repository',
  'roi-synthesis',
  'simpsons-paradox',
]

export const ANALYST_SUB_PHASES: Phase[] = ALL_MODULE_IDS

export interface TickerItem {
  id: string
  label: string
  value: string
  status: 'positive' | 'neutral' | 'warning' | 'negative'
  significant?: boolean
}

export type WorkspaceStatVariant = 'highlight-blue' | 'highlight-green' | 'metric'

export interface WorkspaceStat {
  id: string
  label: string
  value: string
  variant: WorkspaceStatVariant
  priority: number
  minWidth: number
  icon?: import('lucide-react').LucideIcon
  valueTone?: 'positive' | 'default'
  iconTone?: 'accent' | 'default'
}

export interface ThreadItem {
  id: string
  title: string
  timestamp: string
}

export interface ThreadGroup {
  projectId: string
  experiment: string
  threads: ThreadItem[]
}

export type ExperimentDataSourceType = 'internal' | 'external'

export type ProjectChannel = 'digital' | 'store'

export interface ExperimentDataSourceConfig {
  type: ExperimentDataSourceType
  externalConnection?: string
}

export interface Project {
  id: string
  name: string
  description: string
  objective?: string
  channel: ProjectChannel
  dataSource: ExperimentDataSourceConfig
  createdAt: string
}

export interface CreateProjectInput {
  name: string
  description: string
  objective?: string
  channel: ProjectChannel
  dataSource: ExperimentDataSourceConfig
}

export type ChatMessageKind = 'text' | 'module-config' | 'module-run' | 'system' | 'brief-handoff'

interface ChatMessageBase {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export interface TextChatMessage extends ChatMessageBase {
  kind?: 'text'
}

export interface SystemChatMessage extends ChatMessageBase {
  kind: 'system'
  role: 'assistant'
}

export interface ModuleConfigChatMessage extends ChatMessageBase {
  kind: 'module-config'
  role: 'assistant'
  moduleId: ModuleId
}

export interface ModuleRunChatMessage extends ChatMessageBase {
  kind: 'module-run'
  role: 'assistant'
  moduleId: ModuleId
  runId: string
  status: 'running' | 'success' | 'error'
  logs: string[]
  params: Record<string, unknown>
  duration?: string
  evaluation?: ModuleEvaluationPayload
}

export interface BriefHandoffChatMessage extends ChatMessageBase {
  kind: 'brief-handoff'
  role: 'assistant'
  reportId: string
  briefTitle: string
  briefBody: string
  experimentType?: ExperimentTypeChoice
  typeRationale?: string
}

export interface PowerCurveEvaluationPayload {
  targetSampleSize: number
  achievedPower: number
  alpha: number
  beta: number
  mde: number
  baseline: number
  curvePoints: { sampleSize: number; power: number }[]
  durationDays?: number
}

export interface ModuleEvaluationPayload {
  type: 'power-curve' | 'generic'
  summary: string
  powerCurve?: PowerCurveEvaluationPayload
}

export interface ChatReport {
  id: string
  runId: string
  threadId: string
  experiment: string
  moduleId: ModuleId
  title: string
  summary: string
  evaluation?: ModuleEvaluationPayload
  completedAt: string
  duration: string
}

export type ChatMessage =
  | TextChatMessage
  | SystemChatMessage
  | ModuleConfigChatMessage
  | ModuleRunChatMessage
  | BriefHandoffChatMessage

export function getMessageKind(message: ChatMessage): ChatMessageKind {
  return message.kind ?? 'text'
}

export function isModuleRunMessage(message: ChatMessage): message is ModuleRunChatMessage {
  return message.kind === 'module-run'
}

export function isModuleConfigMessage(message: ChatMessage): message is ModuleConfigChatMessage {
  return message.kind === 'module-config'
}

export function isBriefHandoffMessage(message: ChatMessage): message is BriefHandoffChatMessage {
  return message.kind === 'brief-handoff'
}

export interface NewExperimentInput {
  name: string
  hypothesis: string
  goal: string
}

export interface HypothesisValidatorFinalizeInput {
  name: string
  hypothesis: string
  goal: string
  opportunity: Record<string, unknown>
  metrics: Record<string, unknown>
  experimentType: Record<string, unknown>
  power: Record<string, unknown>
  briefTitle: string
  briefBody: string
  funnelStage?: string
  metricsApproved: boolean
  experimentTypeChoice?: ExperimentTypeChoice
  typeRationale?: string
  opportunitySkipped?: boolean
}

export type WorkflowProgressByExperiment = Record<string, Partial<Record<WorkflowStepId, boolean>>>

export type ExperimentSpecsByName = Record<string, ExperimentSpec>

export type LabPanelView = 'tree' | 'form' | 'runs'
export type ModuleRunStatus = 'idle' | 'running' | 'success' | 'error'

export interface ModuleRunRecord {
  id: string
  moduleId: ModuleId
  experiment: string
  params: Record<string, unknown>
  completedAt: string
  duration: string
  status: 'success' | 'error'
}

export type ModuleFormValuesByExperiment = Record<
  string,
  Partial<Record<ModuleId, Record<string, unknown>>>
>

export type ModuleRunsByExperiment = Record<string, ModuleRunRecord[]>

export interface MatchViewState {
  isAuthenticated: boolean
  currentUser: AuthUser | null
  currentPersona: Persona
  currentTab: Tab
  selectedExperiment: string
  activePhase: Phase
  activeModuleId: ModuleId | null
  chartDrawerOpen: boolean
  chartDrawerTargetId: string | null
  highlightedMessageId: string | null
  hypothesisValidatorOpen: boolean
  hypothesisValidatorInitialStep: number | null
  audienceWizardOpen: boolean
  newProjectPanelOpen: boolean
  projects: Project[]
  selectedProjectId: string | null
  experimentProjectIds: Record<string, string>
  experiments: string[]
  threadGroups: ThreadGroup[]
  activeThreadId: string
  messagesByThread: Record<string, ChatMessage[]>
  chatReports: ChatReport[]
  tickerMetrics: WorkspaceStat[]
  labPanelView: LabPanelView
  labModuleId: ModuleId | null
  moduleFormValuesByExperiment: ModuleFormValuesByExperiment
  moduleRunsByExperiment: ModuleRunsByExperiment
  moduleRunStatus: ModuleRunStatus
  analyticsLabCollapsed: boolean
  analyticsLabExpanded: boolean
  highlightedFieldKeys: string[]
  experimentDataSourcesDialogExperiment: string | null
  experimentDataSources: Record<string, ExperimentDataSourceConfig>
  experimentSpecsByName: ExperimentSpecsByName
  workflowProgressByExperiment: WorkflowProgressByExperiment
  pendingModuleActivation: ModuleId | null
  isLlmProcessing: boolean
}

export interface MatchViewActions {
  login: (email: string, password: string) => boolean
  logout: () => void
  setPersona: (persona: Persona) => void
  setTab: (tab: Tab) => void
  setActivePhase: (phase: Phase) => void
  openChartDrawer: (chartId: string) => void
  closeChartDrawer: () => void
  goHome: () => void
  selectProject: (projectId: string) => void
  openNewProjectPanel: () => void
  closeNewProjectPanel: () => void
  knowledgeArchiveOpen: boolean
  openKnowledgeArchive: () => void
  closeKnowledgeArchive: () => void
  createProject: (input: CreateProjectInput) => void
  deleteProject: (projectId: string) => void
  openHypothesisValidator: () => void
  openHypothesisValidatorAtStep: (step: number) => void
  closeHypothesisValidator: () => void
  openAudienceWizard: () => void
  closeAudienceWizard: () => void
  saveAudienceSelection: (values: {
    segment: string
    trafficPercent: number
    exclusions: string
  }) => void
  createExperiment: (input: NewExperimentInput) => void
  finalizeHypothesisValidator: (input: HypothesisValidatorFinalizeInput) => void
  selectThread: (threadId: string, experiment: string) => void
  deleteThread: (threadId: string, experiment: string) => void
  deleteExperiment: (experiment: string) => void
  openExperimentDataSources: (experiment: string) => void
  closeExperimentDataSourcesDialog: () => void
  updateExperimentDataSources: (experiment: string, config: ExperimentDataSourceConfig) => void
  updateExperimentSpec: (experiment: string, patch: Partial<ExperimentSpec>) => void
  markWorkflowStepComplete: (
    experiment: string,
    stepId:
      | 'opportunity-sizing'
      | 'metrics-tracking'
      | 'experiment-type'
      | 'power-calculator'
      | 'audience-selection'
      | 'brief-generator'
      | 'balance-diagnostics',
  ) => void
  clearPendingModuleActivation: () => void
  advanceToWorkflowStep: (moduleId: ModuleId) => void
  selectModule: (moduleId: ModuleId) => void
  clearActiveModule: () => void
  sendMessage: (content: string) => void
  appendChatMessages: (messages: TextChatMessage[]) => void
  executePill: (prompt: string) => void
  scrollToMessage: (messageId: string) => void
  selectLabModule: (moduleId: ModuleId) => void
  updateModuleFormField: (moduleId: ModuleId, key: string, value: unknown) => void
  injectNlpParameters: (
    moduleId: ModuleId,
    params: Record<string, unknown>,
    touchedFields: string[],
  ) => void
  getLockedModuleSnapshot: (moduleId: ModuleId) => Record<string, unknown>
  runActiveLabModule: () => void
  runModule: (moduleId: ModuleId, options?: { skipUserMessage?: boolean; userLabel?: string; paramOverrides?: Record<string, unknown> }) => void
  resetLabToTree: () => void
  toggleAnalyticsLabCollapsed: () => void
  toggleAnalyticsLabExpanded: () => void
  openModuleRun: (runId: string) => void
  setLabPanelView: (view: LabPanelView) => void
  openReport: (reportId: string) => void
}

export type MatchViewContextValue = MatchViewState & MatchViewActions
