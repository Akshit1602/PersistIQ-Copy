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
import {
  fetchExperiments,
  fetchInputSuggestions,
  streamChatResponse,
  type Experiment,
} from '../services/api'
import {
  EXPERIMENTS,
  buildWelcomeMessage,
  formatMessageTime,
  MOCK_MESSAGES,
} from '../data/mock'
import {
  INITIAL_PROJECTS,
  INITIAL_EXPERIMENT_PROJECT_IDS,
  INITIAL_THREAD_GROUPS_WITH_PROJECTS,
} from '../data/projects'
import { buildExecutionLogStream } from '../data/executionService'
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
import { extractNlpParameters } from '../data/nlpParameterExtractor'
import { buildCopilotReport } from '../data/copilotReports'
import {
  prefillableValues,
  suggestFieldValues,
  type DatasetFieldMap,
  type FieldSuggestion,
  type SuggestionContext,
  type SuggestionScope,
} from '../data/inputSuggestions'
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
  type ModuleRunStatus,
  type NewExperimentInput,
  type Persona,
  type Phase,
  type Project,
  type ProjectChannel,
  type Tab,
  type TextChatMessage,
  type BriefHandoffChatMessage,
  type ThreadGroup,
  type UIArtifactCard,
  type WorkflowProgressByExperiment,
  isModuleRunMessage,
} from './types'

export function mapToolToModuleId(toolName: string): ModuleId | null {
  const name = toolName.toLowerCase();
  if (name.includes('srm') || name.includes('health')) return 'health-monitor';
  if (name.includes('power') || name.includes('sample_size') || name.includes('sample-size')) return 'power-calculator';
  if (name.includes('opportunity') || name.includes('validate_hypothesis')) return 'opportunity-sizing';
  if (name.includes('metrics') || name.includes('guardrail')) return 'metrics-tracking';
  if (name.includes('sequential') || name.includes('sprt')) return 'sequential-testing';
  if (name.includes('diff_in_diff') || name.includes('did') || name.includes('causal')) return 'causal-did';
  if (name.includes('forecast') || name.includes('monte_carlo')) return 'forecasting';
  if (name.includes('balance') || name.includes('allocation')) return 'balance-diagnostics';
  if (name.includes('cuped') || name.includes('hypothesis_test') || name.includes('bayesian')) return 'experiment-analysis';
  return null;
}

const INITIAL_EXPERIMENT_SPECS: Record<string, ExperimentSpec> = {
  'Walmart Banner Redesign': {
    name: 'Walmart Banner Redesign',
    hypothesis: 'If we redesign the primary homepage banners with high-contrast borders and clear calls-to-action, homepage CTR will lift by at least 4.2% relative.',
    goal: 'Increase banner click-through rate and checkout-start funnel volume.',
    channel: 'digital',
    experimentType: 'A/B',
    typeRationale: 'Standard A/B test with high-traffic digital touchpoint and 1:1 allocation mapping.',
    funnelStage: 'Discovery',
    metricsApproved: true,
  },
  'Cart Flow Optimization': {
    name: 'Cart Flow Optimization',
    hypothesis: 'If we reduce the checkout flow steps from 4 to 2, cart conversion will lift by 3.5% relative.',
    goal: 'Decrease cart abandonment rate.',
    channel: 'digital',
    experimentType: 'A/B/C',
    typeRationale: 'Standard Multi-variant test to evaluate alternate funnel steps.',
    funnelStage: 'Acquisition',
    metricsApproved: true,
  },
  'Dedicated Cashier Staffing Rollout': {
    name: 'Dedicated Cashier Staffing Rollout',
    hypothesis: 'If we add a dedicated cashier during peak hours in treatment stores, basket conversion will lift by 2.5% relative against a matched control panel.',
    goal: 'Raise store basket conversion without increasing labour cost per transaction.',
    channel: 'store',
    experimentType: 'Causal',
    typeRationale: 'Stores cannot be randomised individually, so lift is measured against a matched control panel.',
    metricsApproved: true,
  },
};

/**
 * Which Insights chart best represents each module's output, used when a report
 * is opened from the Reports list. Ids match MOCK_CHARTS in data/mock.ts plus the
 * dashboard's own card ids ('exposure-trend', 'segment-conversion', 'metric-sheet')
 * — ChartDetectiveDrawer resolves explanations from both sets.
 *
 * Modules with no meaningful chart are deliberately absent: those fall back to
 * DEFAULT_CHART_TARGET rather than pointing at an unrelated visual.
 */
const MODULE_CHART_TARGETS: Partial<Record<ModuleId, string>> = {
  // Revenue / impact framing
  'opportunity-sizing': 'chart-roi',
  forecasting: 'chart-roi',
  'roi-synthesis': 'chart-roi',
  // Traffic, allocation and audience volume
  'power-calculator': 'chart-reach',
  'balance-diagnostics': 'chart-reach',
  'audience-selection': 'chart-reach',
  // Verified statistical outputs
  'health-monitor': 'metric-sheet',
  'sequential-testing': 'metric-sheet',
  'metrics-tracking': 'metric-sheet',
  'distribution-shift': 'metric-sheet',
  // Effect / lift analysis
  'experiment-analysis': 'chart-lift',
  'causal-did': 'chart-lift',
  'simpsons-paradox': 'segment-conversion',
  watchtower: 'exposure-trend',
};

const DEFAULT_CHART_TARGET = 'chart-lift';

const MatchViewContext = createContext<MatchViewContextValue | undefined>(undefined);

let messageCounter = 100;
function nextMessageId() {
  messageCounter += 1;
  return `msg_${messageCounter}_${Date.now()}`;
}
function nextThreadId() {
  return `thread_${Date.now()}`;
}

export const MatchViewProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Auth state
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  // Main UI states
  const [currentPersona, setCurrentPersona] = useState<Persona>('executive');
  const [currentTab, setCurrentTab] = useState<Tab>('chat');
  const [selectedExperiment, setSelectedExperimentState] = useState<string>(EXPERIMENTS[0]);
  const [activePhase, setActivePhase] = useState<Phase>('auto');
  const [activeModuleId, setActiveModuleId] = useState<ModuleId | null>(null);

  // Layout states
  const [chartDrawerOpen, setChartDrawerOpen] = useState<boolean>(false);
  const [chartDrawerTargetId, setChartDrawerTargetId] = useState<string | null>(null);
  const [activeGlobalPage, setActiveGlobalPage] = useState<'workspace' | 'archive' | 'settings'>('workspace');
  const [backendExperiments, setBackendExperiments] = useState<Experiment[]>([]);
  const [chatIsGenerating, setChatIsGenerating] = useState<boolean>(false);
  const [chatActiveToolStatus, setChatActiveToolStatus] = useState<string | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [hypothesisValidatorOpen, setHypothesisValidatorOpen] = useState<boolean>(false);
  const [hypothesisValidatorInitialStep, setHypothesisValidatorInitialStep] = useState<number | null>(null);
  const [audienceWizardOpen, setAudienceWizardOpen] = useState<boolean>(false);
  const [newProjectPanelOpen, setNewProjectPanelOpen] = useState<boolean>(false);
  const [knowledgeArchiveOpen, setKnowledgeArchiveOpen] = useState<boolean>(false);

  // Projects & Experiments Lists
  const [projects, setProjects] = useState<Project[]>(() => structuredClone(INITIAL_PROJECTS));
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [experimentProjectIds, setExperimentProjectIds] = useState<Record<string, string>>(
    () => ({ ...INITIAL_EXPERIMENT_PROJECT_IDS })
  );
  const [experiments, setExperiments] = useState<string[]>([...EXPERIMENTS]);

  // Thread state
  const [threadGroups, setThreadGroupState] = useState<ThreadGroup[]>(
    () => structuredClone(INITIAL_THREAD_GROUPS_WITH_PROJECTS)
  );
  const [activeThreadId, setActiveThreadId] = useState<string>('t1');
  const [messagesByThread, setMessagesByThread] = useState<Record<string, ChatMessage[]>>({
    t1: [...MOCK_MESSAGES],
  });

  // Ticker and reports
  const [chatReports, setChatReports] = useState<ChatReport[]>([]);

  // Analytics Lab panel
  const [labPanelView, setLabPanelView] = useState<LabPanelView>('tree');
  const [labModuleId, setLabModuleId] = useState<ModuleId | null>(null);
  const [moduleFormValuesByExperiment, setModuleFormValuesByExperiment] = useState<ModuleFormValuesByExperiment>({});
  const [moduleRunsByExperiment, setModuleRunsByExperiment] = useState<ModuleRunsByExperiment>(
    () => structuredClone(INITIAL_MODULE_RUNS)
  );
  const [moduleRunStatus, setModuleRunStatus] = useState<ModuleRunStatus>('idle');
  const [analyticsLabCollapsed, setAnalyticsLabCollapsed] = useState<boolean>(false);
  const [analyticsLabExpanded, setAnalyticsLabExpanded] = useState<boolean>(false);
  const [highlightedFieldKeys, setHighlightedFieldKeys] = useState<string[]>([]);

  // Dialog configurations
  const [experimentDataSourcesDialogExperiment, setExperimentDataSourcesDialogExperiment] = useState<string | null>(null);
  const [experimentDataSources, setExperimentDataSources] = useState<Record<string, ExperimentDataSourceConfig>>(
    () => Object.fromEntries(EXPERIMENTS.map((name) => [name, { type: 'internal' as const }]))
  );
  const [experimentSpecsByName, setExperimentSpecsByName] = useState<ExperimentSpecsByName>(INITIAL_EXPERIMENT_SPECS);
  const [workflowProgressByExperiment, setWorkflowProgressByExperiment] = useState<WorkflowProgressByExperiment>({
    'Walmart Banner Redesign': { 'power-calculator': true, 'opportunity-sizing': true },
  });
  const [pendingModuleActivation, setPendingModuleActivation] = useState<ModuleId | null>(null);

  // Baselines derived from each experiment's own data, keyed `experiment|channel`.
  // Fetched once per pair and cached; an unreachable backend leaves the map
  // empty and the suggestion engine falls back to app state.
  const [datasetSuggestionsByKey, setDatasetSuggestionsByKey] = useState<Record<string, DatasetFieldMap>>({});

  const requestedSuggestionKeysRef = useRef<Set<string>>(new Set());
  const runTimeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const highlightTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Single source of truth for the workspace ticker — derived from real
  // experiment/workflow state so it can never disagree with what the rest of
  // the app shows, and never shows fabricated placeholder numbers.
  const tickerMetrics = useMemo(
    () => buildWorkspaceStats(computeLiveExperimentStats(experiments, workflowProgressByExperiment)),
    [experiments, workflowProgressByExperiment]
  );

  // A project's channel decides digital vs store framing for anything created
  // under it. Falls back to 'digital' only when no project is selected yet.
  const channelForProject = useCallback(
    (projectId: string | null): ProjectChannel =>
      projects.find((p) => p.id === projectId)?.channel ?? 'digital',
    [projects]
  );

  const channelForExperiment = useCallback(
    (experiment: string): ProjectChannel => {
      if (experimentSpecsByName[experiment]?.channel === 'store') return 'store';
      const projectId = experimentProjectIds[experiment];
      // An experiment we have not catalogued yet (a wizard draft, say) belongs
      // to whichever project the user is working in.
      return channelForProject(projectId ?? selectedProjectId);
    },
    [experimentSpecsByName, experimentProjectIds, channelForProject, selectedProjectId]
  );

  // Derived baselines are fetched once per experiment/channel pair and cached.
  // Failures resolve to an empty field map inside the service, so a backend
  // that is down simply means fewer suggestions, not a broken form.
  const ensureDatasetSuggestions = useCallback(
    (experiment: string) => {
      if (!experiment) return;
      const channel = channelForExperiment(experiment);
      const key = `${experiment}|${channel}`;
      // Ref-guarded rather than state-guarded so a re-render (or StrictMode's
      // double invoke) cannot fire the same request twice.
      if (requestedSuggestionKeysRef.current.has(key)) return;
      requestedSuggestionKeysRef.current.add(key);

      fetchInputSuggestions(experiment, channel).then((res) => {
        setDatasetSuggestionsByKey((current) => ({ ...current, [key]: res.fields ?? {} }));
      });
    },
    [channelForExperiment]
  );

  useEffect(() => {
    ensureDatasetSuggestions(selectedExperiment);
  }, [selectedExperiment, ensureDatasetSuggestions]);

  const buildSuggestionContext = useCallback(
    (experiment: string): SuggestionContext => {
      const channel = channelForExperiment(experiment);
      const projectId = experimentProjectIds[experiment];
      const siblingValues: Record<string, Partial<Record<ModuleId, Record<string, unknown>>>> = {};
      for (const [name, values] of Object.entries(moduleFormValuesByExperiment)) {
        if (name === experiment) continue;
        if (projectId && experimentProjectIds[name] !== projectId) continue;
        siblingValues[name] = values;
      }

      return {
        experiment,
        channel,
        spec: experimentSpecsByName[experiment],
        moduleValues: moduleFormValuesByExperiment[experiment] ?? {},
        siblingValues,
        datasetFields: datasetSuggestionsByKey[`${experiment}|${channel}`] ?? {},
      };
    },
    [
      channelForExperiment,
      experimentProjectIds,
      experimentSpecsByName,
      moduleFormValuesByExperiment,
      datasetSuggestionsByKey,
    ]
  );

  const getFieldSuggestions = useCallback(
    (
      scope: SuggestionScope,
      experiment?: string,
      overrides?: Partial<SuggestionContext>
    ): Record<string, FieldSuggestion> =>
      suggestFieldValues(scope, {
        ...buildSuggestionContext(experiment ?? selectedExperiment),
        ...(overrides ?? {}),
      }),
    [buildSuggestionContext, selectedExperiment]
  );

  const getSuggestionContext = useCallback(
    (experiment?: string): SuggestionContext =>
      buildSuggestionContext(experiment ?? selectedExperiment),
    [buildSuggestionContext, selectedExperiment]
  );

  const clearRunTimeouts = useCallback(() => {
    runTimeoutsRef.current.forEach(clearTimeout);
    runTimeoutsRef.current = [];
  }, []);

  // Sync / Load logic — real backend fetch. Falls back to the mock fixtures
  // above (already loaded into state) if the backend is unreachable.
  const loadBackendData = async () => {
    try {
      const data: Experiment[] = await fetchExperiments();
      setBackendExperiments(data);
      if (data && data.length > 0) {
        const names = data.map((exp) => exp.name);
        // Merge rather than replace. The backend only knows about experiments it
        // has catalogued, all of which map to the digital projects; replacing
        // outright would drop the store-channel fixtures and leave the store
        // surfaces unreachable.
        setExperiments((prev) => [...new Set([...prev, ...names])]);

        const nextProjectIds: Record<string, string> = {};
        const nextThreadGroups: ThreadGroup[] = [];
        const nextMessagesByThread: Record<string, ChatMessage[]> = {};

        data.forEach((exp, idx) => {
          const projId = idx % 2 === 0 ? 'proj-walmart-digital' : 'proj-cart-reliability';
          nextProjectIds[exp.name] = projId;

          const threadId = `t_backend_${exp.experiment_id}`;
          nextThreadGroups.push({
            projectId: projId,
            experiment: exp.name,
            threads: [
              {
                id: threadId,
                title: `${exp.name} Discussion`,
                timestamp: 'Just now',
              },
            ],
          });

          nextMessagesByThread[threadId] = [
            {
              id: `system_${exp.experiment_id}_init`,
              role: 'assistant',
              content: `This is the discussion thread for **${exp.name}**. Ask me questions about its primary metric (${exp.primary_metric}), sample sizes, or run statistical tests like SRM checks.`,
              timestamp: formatMessageTime(),
              kind: 'text',
              artifacts: [],
            },
          ];
        });

        setExperimentProjectIds((prev) => ({ ...prev, ...nextProjectIds }));
        setThreadGroupState((prev) => {
          const backendExperimentNames = new Set(nextThreadGroups.map((g) => g.experiment));
          // Backend groups win for experiments it knows about; fixture-only
          // groups (the store project) are preserved alongside them.
          return [...prev.filter((g) => !backendExperimentNames.has(g.experiment)), ...nextThreadGroups];
        });
        setMessagesByThread((prev) => ({ ...prev, ...nextMessagesByThread }));

        setSelectedExperimentState(names[0]);
        const firstThread = nextThreadGroups[0]?.threads[0]?.id;
        if (firstThread) {
          setActiveThreadId(firstThread);
        }

        // Dynamically add to specs
        setExperimentSpecsByName((prev) => {
          const next = { ...prev };
          data.forEach((exp) => {
            if (!next[exp.name]) {
              next[exp.name] = {
                name: exp.name,
                hypothesis: `If we optimize ${exp.name}, the primary metric ${exp.primary_metric} will improve.`,
                goal: `Increase ${exp.primary_metric}`,
                channel: 'digital',
                metricsApproved: true,
              };
            }
          });
          return next;
        });
      }
    } catch (err) {
      console.warn('Backend fetch failed, relying on mock data:', err);
    }
  };

  useEffect(() => {
    loadBackendData();
    setChatReports(buildInitialReports());
  }, []);

  useEffect(() => () => clearRunTimeouts(), [clearRunTimeouts]);

  useEffect(() => {
    if (!highlightedMessageId) return;
    const timer = setTimeout(() => setHighlightedMessageId(null), 3000);
    return () => clearTimeout(timer);
  }, [highlightedMessageId]);

  // Actions
  const login = useCallback((email: string, _password?: string): boolean => {
    const trimmed = email.trim();
    if (!trimmed) return false;
    const name = trimmed.split('@')[0];
    setIsAuthenticated(true);
    setCurrentUser({
      name,
      email: trimmed,
      avatarUrl: `https://api.dicebear.com/7.x/personas/svg?seed=${encodeURIComponent(name)}&backgroundColor=132744`,
    });
    return true;
  }, []);

  const logout = useCallback(() => {
    setIsAuthenticated(false);
    setCurrentUser(null);
  }, []);

  const setPersona = useCallback((persona: Persona) => {
    setCurrentPersona(persona);
    if (persona === 'executive') {
      setActiveModuleId(null);
      setLabModuleId(null);
      setLabPanelView('tree');
      setModuleRunStatus('idle');
      clearRunTimeouts();
      setActivePhase((prev) => (ANALYST_SUB_PHASES.includes(prev) ? 'auto' : prev));
    }
  }, [clearRunTimeouts]);

  const setTab = useCallback((tab: Tab) => setCurrentTab(tab), []);

  const selectProject = useCallback((projectId: string) => {
    const project = projects.find((p) => p.id === projectId);
    if (!project) return;

    setSelectedProjectId(projectId);
    setActiveGlobalPage('workspace');
    setHypothesisValidatorOpen(false);
    setAudienceWizardOpen(false);
    setNewProjectPanelOpen(false);

    const projectGroups = threadGroups.filter((g) => g.projectId === projectId);
    const firstGroup = projectGroups[0];
    const firstThread = firstGroup?.threads[0];
    if (firstThread && firstGroup) {
      setActiveThreadId(firstThread.id);
      setSelectedExperimentState(firstGroup.experiment);
    } else {
      const expName =
        Object.entries(experimentProjectIds).find(([, pid]) => pid === projectId)?.[0] ??
        experiments.find((e) => experimentProjectIds[e] === projectId) ??
        '';
      if (expName) setSelectedExperimentState(expName);
      setActiveThreadId('');
    }
    setCurrentTab('chat');
    setActiveModuleId(null);
    setLabModuleId(null);
    setLabPanelView('tree');
  }, [projects, threadGroups, experimentProjectIds, experiments]);

  const createProject = useCallback((input: CreateProjectInput) => {
    const name = input.name.trim();
    if (!name) return;

    const id = 'proj-' + Date.now();
    const project: Project = {
      id,
      name,
      description: input.description.trim(),
      objective: input.objective?.trim() || undefined,
      channel: input.channel,
      dataSource: input.dataSource,
      createdAt: new Date().toISOString().slice(0, 10),
    };

    setProjects((prev) => [project, ...prev]);
    setSelectedProjectId(id);
    setActiveThreadId('');
    setSelectedExperimentState('');
    setCurrentTab('chat');
    setNewProjectPanelOpen(false);
    setActiveModuleId(null);
    setLabModuleId(null);
    setLabPanelView('tree');
  }, []);

  const deleteProject = useCallback((projectId: string) => {
    const expNames = Object.entries(experimentProjectIds)
      .filter(([, pid]) => pid === projectId)
      .map(([name]) => name);

    setProjects((prev) => prev.filter((p) => p.id !== projectId));
    setExperimentProjectIds((prev) => {
      const next = { ...prev };
      expNames.forEach((n) => delete next[n]);
      return next;
    });
    setExperiments((prev) => prev.filter((e) => !expNames.includes(e)));
    setThreadGroupState((prev) => prev.filter((g) => g.projectId !== projectId));
    setMessagesByThread((prev) => {
      const removeIds = new Set(
        threadGroups.filter((g) => g.projectId === projectId).flatMap((g) => g.threads.map((t) => t.id))
      );
      const next = { ...prev };
      removeIds.forEach((id) => delete next[id]);
      return next;
    });
    setChatReports((prev) => prev.filter((r) => !expNames.includes(r.experiment)));
    setExperimentDataSources((prev) => {
      const next = { ...prev };
      expNames.forEach((n) => delete next[n]);
      return next;
    });
    setExperimentSpecsByName((prev) => {
      const next = { ...prev };
      expNames.forEach((n) => delete next[n]);
      return next;
    });
    setWorkflowProgressByExperiment((prev) => {
      const next = { ...prev };
      expNames.forEach((n) => delete next[n]);
      return next;
    });
    setModuleFormValuesByExperiment((prev) => {
      const next = { ...prev };
      expNames.forEach((n) => delete next[n]);
      return next;
    });
    setModuleRunsByExperiment((prev) => {
      const next = { ...prev };
      expNames.forEach((n) => delete next[n]);
      return next;
    });

    if (selectedProjectId === projectId) {
      setSelectedProjectId(null);
      setActiveThreadId('');
      setSelectedExperimentState('');
    }
  }, [experimentProjectIds, threadGroups, selectedProjectId]);

  const openNewProjectPanel = useCallback(() => setNewProjectPanelOpen(true), []);
  const closeNewProjectPanel = useCallback(() => setNewProjectPanelOpen(false), []);

  const openHypothesisValidator = useCallback(() => {
    setHypothesisValidatorInitialStep(null);
    setHypothesisValidatorOpen(true);
  }, []);

  const openHypothesisValidatorAtStep = useCallback((step: number) => {
    setHypothesisValidatorInitialStep(step);
    setHypothesisValidatorOpen(true);
  }, []);

  const closeHypothesisValidator = useCallback(() => {
    setHypothesisValidatorOpen(false);
    setHypothesisValidatorInitialStep(null);
  }, []);

  const openAudienceWizard = useCallback(() => setAudienceWizardOpen(true), []);
  const closeAudienceWizard = useCallback(() => setAudienceWizardOpen(false), []);

  const saveAudienceSelection = useCallback((values: {
    segment: string;
    trafficPercent: number;
    exclusions: string;
  }) => {
    if (!selectedExperiment) return;
    setModuleFormValuesByExperiment((prev) => {
      const expValues = prev[selectedExperiment] || {};
      return {
        ...prev,
        [selectedExperiment]: {
          ...expValues,
          'audience-selection': { ...expValues['audience-selection'], ...values },
        },
      };
    });
    setWorkflowProgressByExperiment((prev) => ({
      ...prev,
      [selectedExperiment]: { ...(prev[selectedExperiment] ?? {}), 'audience-selection': true },
    }));
    setAudienceWizardOpen(false);
  }, [selectedExperiment]);

  const openKnowledgeArchive = useCallback(() => setKnowledgeArchiveOpen(true), []);
  const closeKnowledgeArchive = useCallback(() => setKnowledgeArchiveOpen(false), []);

  const createExperiment = useCallback((input: NewExperimentInput) => {
    const name = input.name.trim();
    if (!name) return;

    const channel = channelForProject(selectedProjectId);
    const spec: ExperimentSpec = {
      name,
      hypothesis: input.hypothesis,
      goal: input.goal,
      channel,
      metricsApproved: false,
    };

    const now = formatMessageTime();
    const welcome: ChatMessage = {
      id: nextMessageId(),
      role: 'assistant',
      content: buildWelcomeMessage(currentPersona, name, spec.hypothesis, spec.goal, channel),
      timestamp: now,
    };
    const similar = findSimilarLearnings(input.hypothesis, input.goal, 3);
    const learningsMessage: ChatMessage = {
      id: nextMessageId(),
      role: 'assistant',
      content: buildSimilarLearningsMessage(similar),
      timestamp: now,
    };

    setExperiments((prev) => [...new Set([...prev, name])]);
    setExperimentSpecsByName((prev) => ({ ...prev, [name]: spec }));

    if (selectedProjectId) {
      setExperimentProjectIds((prev) => ({ ...prev, [name]: selectedProjectId }));
    }

    const threadId = nextThreadId();
    setThreadGroupState((prev) => {
      const existing = prev.find((g) => g.experiment === name);
      if (existing) return prev;
      return [
        ...prev,
        {
          projectId: selectedProjectId || '',
          experiment: name,
          threads: [{ id: threadId, title: 'Discussion', timestamp: 'Just now' }],
        },
      ];
    });

    setActiveThreadId(threadId);
    setMessagesByThread((prev) => ({ ...prev, [threadId]: [welcome, learningsMessage] }));
    const project = projects.find((p) => p.id === selectedProjectId);
    setExperimentDataSources((prev) => ({
      ...prev,
      [name]: prev[name] ?? project?.dataSource ?? { type: 'internal' },
    }));
    setCurrentPersona('analyst');
  }, [currentPersona, selectedProjectId, projects, channelForProject]);

  const finalizeHypothesisValidator = useCallback((input: HypothesisValidatorFinalizeInput) => {
    const name = input.name.trim();
    if (!name) return;

    const channel = channelForProject(selectedProjectId);

    // Create the experiment spec
    const spec: ExperimentSpec = {
      name,
      hypothesis: input.hypothesis,
      goal: input.goal,
      channel,
      experimentType: input.experimentTypeChoice || 'A/B',
      typeRationale: input.typeRationale || 'Auto-derived during validator step.',
      funnelStage: input.funnelStage || 'Discovery',
      metricsApproved: input.metricsApproved,
    };

    setExperimentSpecsByName((prev) => ({ ...prev, [name]: spec }));
    setExperiments((prev) => [...new Set([...prev, name])]);
    setSelectedExperimentState(name);

    if (selectedProjectId) {
      setExperimentProjectIds((prev) => ({ ...prev, [name]: selectedProjectId }));
    }

    // Save validator answers directly as locked module params
    setModuleFormValuesByExperiment((prev) => {
      const nextExp = prev[name] || {};
      return {
        ...prev,
        [name]: {
          ...nextExp,
          'opportunity-sizing': { ...input.opportunity, skipped: input.opportunitySkipped },
          'metrics-tracking': { ...input.metrics, metricsApproved: input.metricsApproved },
          'power-calculator': { ...input.power },
          'experiment-type': {
            experimentType: input.experimentTypeChoice,
            typeRationale: input.typeRationale,
          },
        },
      };
    });

    // Mark steps completed
    setWorkflowProgressByExperiment((prev) => ({
      ...prev,
      [name]: {
        'opportunity-sizing': !input.opportunitySkipped,
        'metrics-tracking': input.metricsApproved,
        'experiment-type': true,
        'power-calculator': true,
      },
    }));

    const now = formatMessageTime();
    const welcome: ChatMessage = {
      id: nextMessageId(),
      role: 'assistant',
      content: buildWelcomeMessage('analyst', name, input.hypothesis, input.goal, channel),
      timestamp: now,
    };
    const similar = findSimilarLearnings(input.hypothesis, input.goal, 3);
    const learningsMessage: ChatMessage = {
      id: nextMessageId(),
      role: 'assistant',
      content: buildSimilarLearningsMessage(similar),
      timestamp: now,
    };

    // Create a new thread with a brief handoff card
    const threadId = nextThreadId();
    const briefBody = buildBriefBody(spec, {
      'opportunity-sizing': input.opportunitySkipped ? { skipped: true } : input.opportunity,
      'metrics-tracking': { ...input.metrics, primaryMetrics: input.metrics.primaryMetricIds },
      'power-calculator': input.power,
      'experiment-type': { experimentType: input.experimentTypeChoice, typeRationale: input.typeRationale },
    });

    const handoffMessage: BriefHandoffChatMessage = {
      id: nextMessageId(),
      role: 'assistant',
      kind: 'brief-handoff',
      reportId: `report_brief_${Date.now()}`,
      briefTitle: `Experiment Brief: ${name}`,
      briefBody,
      content: `Your ${channel} experiment brief has been compiled.`,
      timestamp: now,
      experimentType: spec.experimentType,
      typeRationale: spec.typeRationale,
    };

    setThreadGroupState((prev) => {
      const filtered = prev.filter((g) => g.experiment !== name);
      return [
        ...filtered,
        {
          projectId: selectedProjectId || 'proj-walmart-digital',
          experiment: name,
          threads: [{ id: threadId, title: 'Validator handoff', timestamp: 'Just now' }],
        },
      ];
    });

    setActiveThreadId(threadId);
    setMessagesByThread((prev) => ({ ...prev, [threadId]: [welcome, learningsMessage, handoffMessage] }));

    // Push brief to reports
    setChatReports((prev) => [
      ...prev,
      {
        id: `report_brief_${Date.now()}`,
        runId: `run_brief_${Date.now()}`,
        threadId,
        experiment: name,
        moduleId: 'brief-generator',
        title: `Brief: ${name}`,
        summary: `${channel === 'store' ? 'Store' : 'Digital'} experiment brief for ${name}.`,
        completedAt: 'Just now',
        duration: '1.2s',
      },
    ]);

    setCurrentPersona('analyst');
    setCurrentTab('chat');
    setActiveModuleId(null);
    setLabModuleId(null);
    setLabPanelView('tree');
    setAnalyticsLabCollapsed(false);
    setHypothesisValidatorOpen(false);
  }, [selectedProjectId, projects, channelForProject]);

  const selectThread = useCallback((threadId: string, experiment: string) => {
    setActiveThreadId(threadId);
    setSelectedExperimentState(experiment);
    setCurrentTab('chat');
    setActiveModuleId(null);
    setLabModuleId(null);
    setLabPanelView('tree');
    setModuleRunStatus('idle');
    clearRunTimeouts();
  }, [clearRunTimeouts]);

  const deleteThread = useCallback((threadId: string, experiment: string) => {
    const nextGroups = threadGroups
      .map((g) => (g.experiment === experiment ? { ...g, threads: g.threads.filter((t) => t.id !== threadId) } : g))
      .filter((g) => g.threads.length > 0);

    setThreadGroupState(nextGroups);
    setMessagesByThread((prev) => {
      const { [threadId]: _removed, ...rest } = prev;
      return rest;
    });

    if (activeThreadId === threadId) {
      const fallbackGroup = nextGroups.find((g) => g.experiment === experiment) ?? nextGroups[0];
      const fallback = fallbackGroup?.threads[0];
      if (fallback) {
        setActiveThreadId(fallback.id);
        setSelectedExperimentState(fallbackGroup.experiment);
      }
    }
  }, [threadGroups, activeThreadId]);

  const deleteExperiment = useCallback((experiment: string) => {
    const group = threadGroups.find((g) => g.experiment === experiment);
    const threadIds = new Set(group?.threads.map((t) => t.id) ?? []);
    const remainingGroups = threadGroups.filter((g) => g.experiment !== experiment);

    setThreadGroupState(remainingGroups);
    setExperiments((prev) => prev.filter((e) => e !== experiment));
    setExperimentProjectIds((prev) => {
      const { [experiment]: _removed, ...rest } = prev;
      return rest;
    });
    setMessagesByThread((prev) => {
      const next = { ...prev };
      threadIds.forEach((id) => delete next[id]);
      return next;
    });
    setExperimentDataSources((prev) => {
      const { [experiment]: _removed, ...rest } = prev;
      return rest;
    });
    setExperimentSpecsByName((prev) => {
      const { [experiment]: _removed, ...rest } = prev;
      return rest;
    });
    setWorkflowProgressByExperiment((prev) => {
      const { [experiment]: _removed, ...rest } = prev;
      return rest;
    });
    setExperimentDataSourcesDialogExperiment(null);

    if (threadIds.has(activeThreadId)) {
      const fallbackGroup = remainingGroups[0];
      const fallbackThread = fallbackGroup?.threads[0];
      if (fallbackThread) {
        setActiveThreadId(fallbackThread.id);
        setSelectedExperimentState(fallbackGroup.experiment);
      }
    } else if (selectedExperiment === experiment && remainingGroups[0]) {
      setSelectedExperimentState(remainingGroups[0].experiment);
    }
  }, [threadGroups, activeThreadId, selectedExperiment]);

  const openExperimentDataSources = useCallback((experiment: string) => {
    setExperimentDataSourcesDialogExperiment(experiment);
  }, []);

  const closeExperimentDataSourcesDialog = useCallback(() => {
    setExperimentDataSourcesDialogExperiment(null);
  }, []);

  const updateExperimentDataSources = useCallback((experiment: string, config: ExperimentDataSourceConfig) => {
    setExperimentDataSources((prev) => ({ ...prev, [experiment]: config }));
    setExperimentDataSourcesDialogExperiment(null);
  }, []);

  const updateExperimentSpec = useCallback((experiment: string, patch: Partial<ExperimentSpec>) => {
    setExperimentSpecsByName((prev) => {
      const nextSpec = prev[experiment] ? { ...prev[experiment], ...patch } : (patch as ExperimentSpec);
      return { ...prev, [experiment]: nextSpec };
    });
  }, []);

  const markWorkflowStepComplete = useCallback((experiment: string, stepId: WorkflowStepId) => {
    setWorkflowProgressByExperiment((prev) => ({
      ...prev,
      [experiment]: markStepComplete(prev[experiment] ?? {}, stepId),
    }));
  }, []);

  const flashHighlightedFields = useCallback((keys: string[]) => {
    if (highlightTimeoutRef.current) clearTimeout(highlightTimeoutRef.current);
    setHighlightedFieldKeys(keys);
    highlightTimeoutRef.current = setTimeout(() => {
      setHighlightedFieldKeys([]);
      highlightTimeoutRef.current = null;
    }, 500);
  }, []);

  // Applies smart defaults derived from the experiment's spec/prior module
  // output the first time a module is opened for this experiment, instead of
  // always starting from a blank form.
  const applyLabModuleSelection = useCallback((moduleId: ModuleId, experimentOverride?: string) => {
    const experiment = experimentOverride ?? selectedExperiment;
    setLabModuleId(moduleId);
    setLabPanelView('form');
    setActiveModuleId(moduleId);
    setModuleFormValuesByExperiment((prev) => {
      const experimentValues = prev[experiment] ?? {};
      const schema = getModuleFormSchema(moduleId, experiment);
      let defaults = getDefaultFormValues(schema);
      const spec = experimentSpecsByName[experiment];
      const existing = experimentValues[moduleId];

      // Data-derived and cross-module values land first so the form opens
      // populated; benchmark-grade guesses stay behind a chip in the field UI.
      const suggestions = suggestFieldValues(moduleId, buildSuggestionContext(experiment));
      const { values: suggested } = prefillableValues(suggestions, existing ?? {});
      defaults = { ...defaults, ...suggested };

      if (moduleId === 'metrics-tracking' && spec && !existing) {
        const sizing = experimentValues['opportunity-sizing'];
        const expectedLift = typeof sizing?.expectedLift === 'number' ? sizing.expectedLift : undefined;
        defaults = { ...defaults, ...buildMetricsFormDefaults(spec.hypothesis, spec.goal, expectedLift) };
      }

      if (moduleId === 'experiment-type' && spec && !existing) {
        const sizing = experimentValues['opportunity-sizing'];
        const expectedLift = typeof sizing?.expectedLift === 'number' ? sizing.expectedLift : undefined;
        defaults = { ...defaults, ...buildExperimentTypeDefaults(spec.hypothesis, spec.goal, expectedLift) };
      }

      if (moduleId === 'brief-generator' && spec) {
        defaults = {
          ...(existing ?? defaults),
          briefTitle: `${spec.name} — ${spec.channel === 'store' ? 'Store' : 'Digital'} Experiment Brief`,
          briefBody: buildBriefBody(spec, {
            ...experimentValues,
            ...(existing ? { 'brief-generator': existing } : {}),
          }),
        };
        return { ...prev, [experiment]: { ...experimentValues, [moduleId]: defaults } };
      }

      if (existing) {
        // Re-opening a configured module only fills gaps — a field the user
        // already answered is never rewritten, but one left blank picks up a
        // suggestion that arrived after the first open.
        if (Object.keys(suggested).length === 0) return prev;
        return {
          ...prev,
          [experiment]: { ...experimentValues, [moduleId]: { ...existing, ...suggested } },
        };
      }
      return { ...prev, [experiment]: { ...experimentValues, [moduleId]: defaults } };
    });
  }, [selectedExperiment, experimentSpecsByName, buildSuggestionContext]);

  const clearPendingModuleActivation = useCallback(() => setPendingModuleActivation(null), []);

  const advanceToWorkflowStep = useCallback((moduleId: ModuleId) => {
    setAnalyticsLabCollapsed(false);
    setCurrentPersona('analyst');
    applyLabModuleSelection(moduleId);
    setPendingModuleActivation(moduleId);
  }, [applyLabModuleSelection]);

  const selectModule = useCallback((moduleId: ModuleId) => {
    setActiveModuleId(moduleId);
  }, []);

  const clearActiveModule = useCallback(() => setActiveModuleId(null), []);

  const selectLabModule = useCallback((moduleId: ModuleId) => {
    setAnalyticsLabCollapsed(false);
    applyLabModuleSelection(moduleId);
  }, [applyLabModuleSelection]);

  const updateModuleFormField = useCallback((moduleId: ModuleId, key: string, value: unknown) => {
    setModuleFormValuesByExperiment((prev) => {
      const expValues = prev[selectedExperiment] || {};
      const modValues = expValues[moduleId] || {};
      return {
        ...prev,
        [selectedExperiment]: { ...expValues, [moduleId]: { ...modValues, [key]: value } },
      };
    });
  }, [selectedExperiment]);

  const injectNlpParameters = useCallback((
    moduleId: ModuleId,
    params: Record<string, unknown>,
    touchedFields: string[]
  ) => {
    setAnalyticsLabCollapsed(false);
    applyLabModuleSelection(moduleId);
    setModuleFormValuesByExperiment((prev) => {
      const expValues = prev[selectedExperiment] || {};
      const modValues = expValues[moduleId] || {};
      return {
        ...prev,
        [selectedExperiment]: { ...expValues, [moduleId]: { ...modValues, ...params } },
      };
    });
    flashHighlightedFields(touchedFields);
  }, [applyLabModuleSelection, selectedExperiment, flashHighlightedFields]);

  const getLockedModuleSnapshot = useCallback((moduleId: ModuleId) => {
    const base =
      moduleFormValuesByExperiment[selectedExperiment]?.[moduleId] ??
      getDefaultFormValues(getModuleFormSchema(moduleId, selectedExperiment));
    return structuredClone(base);
  }, [moduleFormValuesByExperiment, selectedExperiment]);

  const runModule = useCallback((
    moduleId: ModuleId,
    options?: { skipUserMessage?: boolean; userLabel?: string; paramOverrides?: Record<string, unknown> }
  ) => {
    if (moduleRunStatus === 'running' || !activeThreadId) return;

    clearRunTimeouts();
    const params = { ...getLockedModuleSnapshot(moduleId), ...(options?.paramOverrides ?? {}) };
    const steps = buildExecutionLogStream(moduleId, params, selectedExperiment);
    const mod = MODULE_BY_ID[moduleId];
    const now = formatMessageTime();
    const runId = 'run-' + Date.now();
    const runMessageId = nextMessageId();
    const threadId = activeThreadId;

    const userMessage: TextChatMessage | null = options?.skipUserMessage
      ? null
      : {
          kind: 'text',
          id: nextMessageId(),
          role: 'user',
          content: options?.userLabel ?? `Run ${mod?.label ?? moduleId} on ${selectedExperiment}`,
          timestamp: now,
        };

    const runMessage: ModuleRunChatMessage = {
      kind: 'module-run',
      id: runMessageId,
      role: 'assistant',
      content: `Running ${mod?.label ?? moduleId}…`,
      timestamp: now,
      moduleId,
      runId,
      status: 'running',
      logs: [],
      params,
    };

    setModuleRunStatus('running');
    applyLabModuleSelection(moduleId);
    setMessagesByThread((prev) => {
      const existing = prev[threadId] ?? [];
      const nextMessages = userMessage ? [...existing, userMessage, runMessage] : [...existing, runMessage];
      return { ...prev, [threadId]: nextMessages };
    });
    setHighlightedMessageId(runMessageId);

    steps.forEach((step) => {
      const timeout = setTimeout(() => {
        setMessagesByThread((prev) => {
          const msgs = prev[threadId] ?? [];
          return {
            ...prev,
            [threadId]: msgs.map((m) =>
              m.id === runMessageId && isModuleRunMessage(m) ? { ...m, logs: [...m.logs, step.line] } : m
            ),
          };
        });
      }, step.delayMs);
      runTimeoutsRef.current.push(timeout);
    });

    const completeTimeout = setTimeout(() => {
      const record: ModuleRunRecord = {
        id: runId,
        moduleId,
        experiment: selectedExperiment,
        params,
        completedAt: formatMessageTime(),
        duration: mod?.mockDuration ?? '2.5s',
        status: 'success',
      };

      setModuleFormValuesByExperiment((prev) => ({
        ...prev,
        [selectedExperiment]: { ...(prev[selectedExperiment] ?? {}), [moduleId]: params },
      }));
      setModuleRunsByExperiment((prev) => ({
        ...prev,
        [selectedExperiment]: [record, ...(prev[selectedExperiment] ?? [])].slice(0, 20),
      }));
      setActiveModuleId(moduleId);
      setModuleRunStatus('success');

      const evaluation = buildModuleEvaluation(moduleId, params);

      if (isWorkflowStepId(moduleId)) {
        const canComplete = moduleId !== 'metrics-tracking' || Boolean(String(params.featureDescription ?? '').trim());
        if (canComplete) {
          setWorkflowProgressByExperiment((prev) => ({
            ...prev,
            [selectedExperiment]: markStepComplete(prev[selectedExperiment] ?? {}, moduleId),
          }));
        }
      }

      if (moduleId === 'metrics-tracking') {
        setExperimentSpecsByName((prev) => {
          const existing = prev[selectedExperiment];
          if (!existing) return prev;
          return {
            ...prev,
            [selectedExperiment]: {
              ...existing,
              metricsApproved: Boolean(String(params.featureDescription ?? '').trim()),
            },
          };
        });
      }

      if (moduleId === 'experiment-type') {
        setExperimentSpecsByName((prev) => {
          const existing = prev[selectedExperiment];
          if (!existing) return prev;
          return {
            ...prev,
            [selectedExperiment]: {
              ...existing,
              experimentType: (params.experimentType as ExperimentSpec['experimentType']) ?? 'A/B',
              typeRationale: String(params.typeRationale ?? ''),
            },
          };
        });
      }

      const report: ChatReport = {
        id: `report-${runId}`,
        runId,
        threadId,
        experiment: selectedExperiment,
        moduleId,
        title: `${mod?.label ?? moduleId} Report`,
        summary: evaluation.summary,
        evaluation,
        completedAt: formatMessageTime(),
        duration: mod?.mockDuration ?? '2.5s',
      };
      setChatReports((prev) => [report, ...prev]);

      setMessagesByThread((prev) => {
        const msgs = prev[threadId] ?? [];
        return {
          ...prev,
          [threadId]: msgs.map((m) =>
            m.id === runMessageId && isModuleRunMessage(m)
              ? { ...m, status: 'success' as const, duration: mod?.mockDuration ?? '2.5s', evaluation, content: evaluation.summary }
              : m
          ),
        };
      });
    }, (steps[steps.length - 1]?.delayMs ?? 0) + 200);
    runTimeoutsRef.current.push(completeTimeout);
  }, [moduleRunStatus, activeThreadId, selectedExperiment, clearRunTimeouts, applyLabModuleSelection, getLockedModuleSnapshot]);

  const runActiveLabModule = useCallback(() => {
    if (!labModuleId || moduleRunStatus === 'running') return;
    runModule(labModuleId);
  }, [labModuleId, moduleRunStatus, runModule]);

  const resetLabToTree = useCallback(() => {
    setLabPanelView('tree');
    setLabModuleId(null);
  }, []);

  const toggleAnalyticsLabCollapsed = useCallback(() => setAnalyticsLabCollapsed((prev) => !prev), []);
  const toggleAnalyticsLabExpanded = useCallback(() => setAnalyticsLabExpanded((prev) => !prev), []);

  const setLabPanelViewState = useCallback((view: LabPanelView) => {
    setLabPanelView(view);
    if (view === 'tree') setLabModuleId(null);
  }, []);

  const scrollToMessage = useCallback((messageId: string) => {
    setHighlightedMessageId(messageId);
    setCurrentTab('chat');
  }, []);

  const openModuleRun = useCallback((runId: string) => {
    const runs = moduleRunsByExperiment[selectedExperiment] ?? [];
    const run = runs.find((r) => r.id === runId);
    if (!run) return;

    setModuleFormValuesByExperiment((prev) => ({
      ...prev,
      [selectedExperiment]: { ...(prev[selectedExperiment] ?? {}), [run.moduleId]: run.params },
    }));
    setActiveModuleId(run.moduleId);
    setLabModuleId(run.moduleId);
    setLabPanelView('form');
    setCurrentTab('chat');

    const threadMessages = messagesByThread[activeThreadId] ?? [];
    const runMessage = threadMessages.find((m) => isModuleRunMessage(m) && m.runId === runId);
    if (runMessage) scrollToMessage(runMessage.id);
  }, [moduleRunsByExperiment, selectedExperiment, messagesByThread, activeThreadId, scrollToMessage]);

  // Real backend chat over SSE — tokens, tool-execution badges, and artifact
  // cards stream from continum. This is intentionally the only chat path:
  // no client-side LLM call, no local fabricated reply.
  const sendMessage = useCallback((content: string) => {
    if (!content.trim() || chatIsGenerating) return;

    // Accumulated outside React state because the SSE callbacks fire faster
    // than state settles, and the report built at onDone needs the whole turn.
    const turn = { artifacts: [] as UIArtifactCard[], tools: [] as string[], text: '' };

    const timestamp = formatMessageTime();
    const userMsg: ChatMessage = {
      id: 'msg_user_' + Date.now(),
      role: 'user',
      content,
      timestamp,
      kind: 'text',
    };

    const threadId = activeThreadId || 'matchview_session';

    setMessagesByThread((prev) => {
      const list = prev[threadId] || [];
      return { ...prev, [threadId]: [...list, userMsg] };
    });

    const assistantMsgId = 'msg_asst_' + Date.now();
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      timestamp: formatMessageTime(),
      kind: 'text',
      artifacts: [],
    };

    setMessagesByThread((prev) => {
      const list = prev[threadId] || [];
      return { ...prev, [threadId]: [...list, assistantMsg] };
    });

    if (currentPersona === 'analyst') {
      const nlp = extractNlpParameters(
        content,
        selectedExperiment,
        activeModuleId,
        buildSuggestionContext(selectedExperiment)
      );
      if (nlp) {
        injectNlpParameters(nlp.moduleId, nlp.params, nlp.touchedFields);
      }
    }

    setChatIsGenerating(true);
    setChatActiveToolStatus('Analyzing request...');

    const activeBackendExp = backendExperiments.find((e) => e.name === selectedExperiment);
    const activeExperimentId = activeBackendExp ? activeBackendExp.experiment_id : null;

    streamChatResponse({
      message: content,
      threadId,
      activeExperimentId,
      onToken: (chunk) => {
        setChatActiveToolStatus(null);
        turn.text += chunk;
        setMessagesByThread((prev) => {
          const list = prev[threadId] || [];
          return {
            ...prev,
            [threadId]: list.map((msg) => (msg.id === assistantMsgId ? { ...msg, content: msg.content + chunk } : msg)),
          };
        });
      },
      onToolStart: (tool, statusMsg) => {
        setChatActiveToolStatus(statusMsg);
        turn.tools.push(tool);
        if (currentPersona === 'analyst') {
          const mappedModuleId = mapToolToModuleId(tool);
          if (mappedModuleId) {
            applyLabModuleSelection(mappedModuleId);
            const nlp = extractNlpParameters(
              content,
              selectedExperiment,
              mappedModuleId,
              buildSuggestionContext(selectedExperiment)
            );
            if (nlp) {
              injectNlpParameters(nlp.moduleId, nlp.params, nlp.touchedFields);
            }
          }
        }
      },
      onArtifact: (artifactPayload) => {
        const card: UIArtifactCard = {
          artifact_id: artifactPayload.artifact_id || `art_${Date.now()}`,
          type: artifactPayload.type || 'stat_results_card',
          title: artifactPayload.title || 'Analysis Card',
          payload: artifactPayload.payload || artifactPayload,
        };
        turn.artifacts.push(card);

        setMessagesByThread((prev) => {
          const list = prev[threadId] || [];
          return {
            ...prev,
            [threadId]: list.map((msg) => {
              if (msg.id === assistantMsgId) {
                const existingArtifacts = msg.artifacts || [];
                return { ...msg, artifacts: [...existingArtifacts, card] };
              }
              return msg;
            }),
          };
        });
      },
      onDone: () => {
        setChatIsGenerating(false);
        setChatActiveToolStatus(null);

        // Anything the Copilot actually produced — a chart, a stat card — is an
        // analytical output and belongs in Reports alongside module runs.
        // Reports previously only ever came from local module runs, so a chat
        // turn that computed a real result left no trace on the tab.
        const report = buildCopilotReport({
          artifacts: turn.artifacts,
          toolNames: turn.tools,
          answerText: turn.text,
          prompt: content,
          experiment: selectedExperiment,
          threadId,
        });
        if (report) setChatReports((prev) => [report, ...prev]);
      },
      onError: (err) => {
        console.error('Chat streaming error:', err);
        setChatIsGenerating(false);
        setChatActiveToolStatus(null);
        setMessagesByThread((prev) => {
          const list = prev[threadId] || [];
          return {
            ...prev,
            [threadId]: list.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, content: '⚠️ Unable to connect to backend AI assistant. Make sure the backend server is running.' }
                : msg
            ),
          };
        });
      },
    });
  }, [chatIsGenerating, activeThreadId, currentPersona, selectedExperiment, activeModuleId, backendExperiments, applyLabModuleSelection, injectNlpParameters, buildSuggestionContext]);

  const executePill = useCallback((prompt: string) => sendMessage(prompt), [sendMessage]);

  const appendChatMessages = useCallback((messages: TextChatMessage[]) => {
    if (!activeThreadId || messages.length === 0) return;
    setMessagesByThread((prev) => ({
      ...prev,
      [activeThreadId]: [...(prev[activeThreadId] || []), ...messages],
    }));
  }, [activeThreadId]);

  const openChartDrawer = useCallback((chartId: string) => {
    setChartDrawerOpen(true);
    setChartDrawerTargetId(chartId);
  }, []);

  const closeChartDrawer = useCallback(() => {
    setChartDrawerOpen(false);
    setChartDrawerTargetId(null);
  }, []);

  const goHome = useCallback(() => {
    setCurrentTab('chat');
    setActivePhase('auto');
    setActiveGlobalPage('workspace');
    setSelectedProjectId(null);
    setNewProjectPanelOpen(false);
    setHypothesisValidatorOpen(false);
    setAudienceWizardOpen(false);
    setActiveModuleId(null);
    setLabModuleId(null);
    setLabPanelView('tree');
  }, []);

  // Called from the Reports list's "Open in Insights" action. Brief-generator
  // reports open the Reports tab directly (there is no dedicated brief chart);
  // everything else navigates to Insights and opens the chart that represents
  // the report's module, so the click lands somewhere specific.
  const openReport = useCallback((reportId: string) => {
    const report = chatReports.find((r) => r.id === reportId);
    if (!report) return;

    setSelectedExperimentState(report.experiment);
    setActiveThreadId(report.threadId);
    setActiveModuleId(report.moduleId);

    // A report that carries its own charts already shows everything it has, and
    // a Copilot report with no module has no Insights chart to point at. Both
    // stay on Reports rather than jumping to an unrelated visual.
    if (report.moduleId === 'brief-generator' || report.artifacts?.length || !report.moduleId) {
      setCurrentTab('reports');
      return;
    }

    setCurrentTab('insights');
    openChartDrawer(MODULE_CHART_TARGETS[report.moduleId] ?? DEFAULT_CHART_TARGET);
  }, [chatReports, openChartDrawer]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeChartDrawer();
        setHypothesisValidatorOpen(false);
        setNewProjectPanelOpen(false);
        setExperimentDataSourcesDialogExperiment(null);
        setKnowledgeArchiveOpen(false);
        setHighlightedMessageId(null);
        return;
      }
      if (
        (e.metaKey || e.ctrlKey) &&
        e.key === 'Enter' &&
        currentPersona === 'analyst' &&
        labModuleId &&
        moduleRunStatus !== 'running'
      ) {
        e.preventDefault();
        runActiveLabModule();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [closeChartDrawer, currentPersona, labModuleId, moduleRunStatus, runActiveLabModule]);

  return (
    <MatchViewContext.Provider
      value={{
        isAuthenticated,
        currentUser,
        currentPersona,
        currentTab,
        selectedExperiment,
        activePhase,
        activeModuleId,
        chartDrawerOpen,
        chartDrawerTargetId,
        highlightedMessageId,
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
        activeGlobalPage,
        setActiveGlobalPage,
        chatIsGenerating,
        chatActiveToolStatus,
        knowledgeArchiveOpen,
        datasetSuggestionFields:
          datasetSuggestionsByKey[
            `${selectedExperiment}|${channelForExperiment(selectedExperiment)}`
          ] ?? {},
        getFieldSuggestions,
        getSuggestionContext,
        ensureDatasetSuggestions,
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
      }}
    >
      {children}
    </MatchViewContext.Provider>
  );
};

export const useMatchView = () => {
  const context = useContext(MatchViewContext);
  if (!context) {
    throw new Error('useMatchView must be used within a MatchViewProvider');
  }
  return context;
};
