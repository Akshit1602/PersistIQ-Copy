import type { WorkflowStepId } from '../data/hypothesisWorkflow'
import type {
  DatasetFieldMap,
  FieldSuggestion,
  SuggestionContext,
  SuggestionScope,
} from '../data/inputSuggestions'

export type Persona = 'executive' | 'analyst'
export type Tab = 'chat' | 'insights' | 'reports'

export interface AuthUser {
  name: string
  email: string
  avatarUrl: string
}

export type ExecutivePhase = 'auto' | 'discovery' | 'planning' | 'monitoring' | 'analysis'

export type ProjectChannel = 'digital' | 'store'

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

/** An experiment inherits its channel from the project it belongs to, so this
 * must cover every ProjectChannel — not just 'digital'. */
export type ExperimentChannel = ProjectChannel
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

/** Chart shapes the backend emits. Mirrors `ChartKind` in
 * continum/AskData/chart_spec.py. */
export type ChartKind = 'bar' | 'grouped_bar' | 'line' | 'area' | 'pie' | 'scatter'

export interface ChartSeriesSpec {
  name: string
  /** Index-aligned with `categories`. null is a gap, not a zero. */
  values: (number | null)[]
  color?: string | null
  /** Symmetric half-width error bars, e.g. a confidence interval. */
  error?: (number | null)[] | null
}

/**
 * A renderer-neutral chart, mirroring `ChartSpec` in
 * continum/AskData/chart_spec.py. The backend also produces Plotly JSON, but
 * MatchView draws its own SVG from this so charts match the rest of the app —
 * see ArtifactChart.
 */
export interface ChartSpec {
  kind: ChartKind
  title: string
  categories: string[]
  series: ChartSeriesSpec[]
  x_title: string
  y_title: string
  value_format: 'number' | 'currency' | 'percent'
  /** Caveats about the picture (truncation, dropped series). Shown as a caption. */
  notes: string[]
}

/** A structured card streamed from the backend over SSE alongside chat text
 * (see `UIArtifact` in continum/state.py). Rendered by ArtifactCardRenderer. */
export interface UIArtifactCard {
  artifact_id: string
  type: string
  title: string
  payload: Record<string, unknown>
}

/** True when the card carries a chart spec the SVG renderer can draw. The type
 * tag alone is not enough — a malformed payload must fall back to the metric
 * grid rather than crash the chat stream. */
export function isChartArtifact(card: UIArtifactCard): boolean {
  if (card.type !== 'plotly_chart') return false
  const spec = card.payload?.chart_spec as ChartSpec | undefined
  return Boolean(spec && Array.isArray(spec.categories) && Array.isArray(spec.series))
}

export type ChatMessageKind = 'text' | 'module-config' | 'module-run' | 'system' | 'brief-handoff'

interface ChatMessageBase {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  artifacts?: UIArtifactCard[]
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

/** Where a report came from: an Analytics Lab module run, or a Copilot chat turn
 * that produced analysis or a chart. */
export type ReportSource = 'module' | 'copilot'

export interface ChatReport {
  id: string
  runId: string
  threadId: string
  experiment: string
  /** null for a Copilot turn that maps to no Analytics Lab module — a chart of
   * an ad-hoc query belongs to no module, and forcing one would file it under
   * an analysis that never ran. */
  moduleId: ModuleId | null
  title: string
  summary: string
  evaluation?: ModuleEvaluationPayload
  /** Charts and stat cards produced by the turn, rendered inline in Reports. */
  artifacts?: UIArtifactCard[]
  source?: ReportSource
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
  activeGlobalPage: 'workspace' | 'archive' | 'settings'
  chatIsGenerating: boolean
  chatActiveToolStatus: string | null
  knowledgeArchiveOpen: boolean
  /** Backend-derived baselines for the selected experiment, keyed by form field. */
  datasetSuggestionFields: DatasetFieldMap
}

export interface MatchViewActions {
  setActiveGlobalPage: (page: 'workspace' | 'archive' | 'settings') => void
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
  createProject: (input: CreateProjectInput) => void
  deleteProject: (projectId: string) => void
  openHypothesisValidator: () => void
  closeHypothesisValidator: () => void
  openHypothesisValidatorAtStep: (step: number) => void
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
  openKnowledgeArchive: () => void
  closeKnowledgeArchive: () => void
  /**
   * Best suggestion per field for a scope, sourced dataset-first and app-state
   * second. Pass an experiment to score a different one from the selected.
   */
  getFieldSuggestions: (
    scope: SuggestionScope,
    experiment?: string,
    /** In-flight state a wizard holds but has not committed yet (draft spec). */
    overrides?: Partial<SuggestionContext>,
  ) => Record<string, FieldSuggestion>
  /** Everything the suggestion engine needs, for callers that run it themselves. */
  getSuggestionContext: (experiment?: string) => SuggestionContext
  /** Fetches and caches an experiment's derived baselines if not already held. */
  ensureDatasetSuggestions: (experiment: string) => void
}

export type MatchViewContextValue = MatchViewState & MatchViewActions
