import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { fetchExperiments, streamChatResponse, type Experiment } from '../services/api';
import type {
  AuthUser,
  Persona,
  Tab,
  Phase,
  ModuleId,
  ThreadGroup,
  Project,
  ChatMessage,
  ChatReport,
  WorkspaceStat,
  LabPanelView,
  ModuleRunStatus,
  ExperimentDataSourceConfig,
  ExperimentSpecsByName,
  WorkflowProgressByExperiment,
  MatchViewContextValue,
  ModuleFormValuesByExperiment,
  ModuleRunsByExperiment,
  NewExperimentInput,
  HypothesisValidatorFinalizeInput,
  ExperimentSpec,
  TextChatMessage,
} from './types';

import {
  INITIAL_PROJECTS,
  INITIAL_EXPERIMENT_PROJECT_IDS,
  INITIAL_THREAD_GROUPS_WITH_PROJECTS,
} from '../data/projects';

import {
  EXPERIMENTS,
  buildWelcomeMessage,
  formatMessageTime,
  MOCK_MESSAGES,
} from '../data/mock';

import { buildInitialReports } from '../data/initialReports';
import { WORKSPACE_STATS } from '../data/workspaceStats';
import { INITIAL_MODULE_RUNS } from '../data/initialModuleRuns';
import { MODULE_BY_ID } from '../data/moduleRegistry';
import { buildModuleEvaluation } from '../data/moduleEvaluation';
import { isWorkflowStepId } from '../data/hypothesisWorkflow';
import { buildBriefBody } from '../data/briefBuilder';
import { extractNlpParameters } from '../data/nlpParameterExtractor';

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
};

const MatchViewContext = createContext<MatchViewContextValue | undefined>(undefined);

export const MatchViewProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Auth state
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  // Main UI states
  const [currentPersona, setCurrentPersona] = useState<Persona>('executive');
  const [currentTab, setCurrentTab] = useState<Tab>('chat');
  const [selectedExperiment, setSelectedExperiment] = useState<string>('Walmart Banner Redesign');
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
  const [projects, setProjects] = useState<Project[]>(INITIAL_PROJECTS);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>('proj-walmart-digital');
  const [experimentProjectIds, setExperimentProjectIds] = useState<Record<string, string>>(
    INITIAL_EXPERIMENT_PROJECT_IDS
  );
  const [experiments, setExperiments] = useState<string[]>([...EXPERIMENTS]);

  // Thread state
  const [threadGroups, setThreadGroupState] = useState<ThreadGroup[]>(
    INITIAL_THREAD_GROUPS_WITH_PROJECTS
  );
  const [activeThreadId, setActiveThreadId] = useState<string>('t1');
  const [messagesByThread, setMessagesByThread] = useState<Record<string, ChatMessage[]>>({
    t1: [...MOCK_MESSAGES],
  });

  // Ticker and reports
  const [chatReports, setChatReports] = useState<ChatReport[]>([]);
  const [tickerMetrics] = useState<WorkspaceStat[]>(WORKSPACE_STATS);

  // Analytics Lab panel
  const [labPanelView, setLabPanelView] = useState<LabPanelView>('tree');
  const [labModuleId, setLabModuleId] = useState<ModuleId | null>(null);
  const [moduleFormValuesByExperiment, setModuleFormValuesByExperiment] = useState<ModuleFormValuesByExperiment>({});
  const [moduleRunsByExperiment, setModuleRunsByExperiment] = useState<ModuleRunsByExperiment>(
    INITIAL_MODULE_RUNS
  );
  const [moduleRunStatus, setModuleRunStatus] = useState<ModuleRunStatus>('idle');
  const [analyticsLabCollapsed, setAnalyticsLabCollapsed] = useState<boolean>(false);
  const [analyticsLabExpanded, setAnalyticsLabExpanded] = useState<boolean>(false);
  const [isLlmProcessing] = useState<boolean>(false);
  const [highlightedFieldKeys, setHighlightedFieldKeys] = useState<string[]>([]);

  // Dialog configurations
  const [experimentDataSourcesDialogExperiment, setExperimentDataSourcesDialogExperiment] = useState<string | null>(null);
  const [experimentDataSources, setExperimentDataSources] = useState<Record<string, ExperimentDataSourceConfig>>({});
  const [experimentSpecsByName, setExperimentSpecsByName] = useState<ExperimentSpecsByName>(INITIAL_EXPERIMENT_SPECS);
  const [workflowProgressByExperiment, setWorkflowProgressByExperiment] = useState<WorkflowProgressByExperiment>({
    'Walmart Banner Redesign': { 'power-calculator': true, 'opportunity-sizing': true },
  });
  const [pendingModuleActivation, setPendingModuleActivation] = useState<ModuleId | null>(null);

  // Sync / Load logic
  const loadBackendData = async () => {
    try {
      const data: Experiment[] = await fetchExperiments();
      setBackendExperiments(data);
      if (data && data.length > 0) {
        const names = data.map((exp) => exp.name);
        setExperiments(names);

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

        setExperimentProjectIds(nextProjectIds);
        setThreadGroupState(nextThreadGroups);
        setMessagesByThread(nextMessagesByThread);

        setSelectedExperiment(names[0]);
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
      } else {
        setExperiments([]);
      }
    } catch (err) {
      console.warn('Backend fetch failed, relying on mock data:', err);
    }
  };

  useEffect(() => {
    loadBackendData();
    // Initialize reports
    setChatReports(buildInitialReports());
  }, []);

  // Actions
  const login = (email: string, _password?: string): boolean => {
    if (email.trim().length > 0) {
      setIsAuthenticated(true);
      setCurrentUser({
        name: email.split('@')[0],
        email,
        avatarUrl: '',
      });
      return true;
    }
    return false;
  };

  const logout = () => {
    setIsAuthenticated(false);
    setCurrentUser(null);
  };

  const selectProject = (projectId: string) => {
    setSelectedProjectId(projectId);
  };

  const createProject = (input: any) => {
    const newProj: Project = {
      id: 'proj-' + Date.now(),
      name: input.name,
      description: input.description,
      objective: input.objective,
      channel: input.channel,
      dataSource: input.dataSource,
      createdAt: new Date().toISOString().split('T')[0],
    };
    setProjects((prev) => [...prev, newProj]);
    setSelectedProjectId(newProj.id);
    setNewProjectPanelOpen(false);
  };

  const deleteProject = (projectId: string) => {
    setProjects((prev) => prev.filter((p) => p.id !== projectId));
    if (selectedProjectId === projectId) {
      setSelectedProjectId(null);
    }
  };

  const openNewProjectPanel = () => setNewProjectPanelOpen(true);
  const closeNewProjectPanel = () => setNewProjectPanelOpen(false);

  const openKnowledgeArchive = () => setKnowledgeArchiveOpen(true);
  const closeKnowledgeArchive = () => setKnowledgeArchiveOpen(false);

  const openHypothesisValidator = () => setHypothesisValidatorOpen(true);
  const openHypothesisValidatorAtStep = (step: number) => {
    setHypothesisValidatorInitialStep(step);
    setHypothesisValidatorOpen(true);
  };
  const closeHypothesisValidator = () => {
    setHypothesisValidatorOpen(false);
    setHypothesisValidatorInitialStep(null);
  };

  const openAudienceWizard = () => setAudienceWizardOpen(true);
  const closeAudienceWizard = () => setAudienceWizardOpen(false);

  const saveAudienceSelection = (values: {
    segment: string;
    trafficPercent: number;
    exclusions: string;
  }) => {
    // Inject values to audience-selection module state
    setModuleFormValuesByExperiment((prev) => {
      const expValues = prev[selectedExperiment] || {};
      return {
        ...prev,
        [selectedExperiment]: {
          ...expValues,
          'audience-selection': {
            ...expValues['audience-selection'],
            ...values,
          },
        },
      };
    });
    setAudienceWizardOpen(false);
  };

  const createExperiment = (input: NewExperimentInput) => {
    const name = input.name.trim();
    if (!name) return;

    setExperiments((prev) => [...new Set([...prev, name])]);
    setSelectedExperiment(name);

    const spec: ExperimentSpec = {
      name,
      hypothesis: input.hypothesis,
      goal: input.goal,
      channel: 'digital',
      metricsApproved: false,
    };

    setExperimentSpecsByName((prev) => ({
      ...prev,
      [name]: spec,
    }));

    // Setup project association
    if (selectedProjectId) {
      setExperimentProjectIds((prev) => ({
        ...prev,
        [name]: selectedProjectId,
      }));
    }

    // Initialize blank thread for this experiment
    const threadId = 'thread_' + Date.now();
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
    setMessagesByThread((prev) => ({
      ...prev,
      [threadId]: [
        {
          id: 'welcome_' + Date.now(),
          role: 'assistant',
          content: buildWelcomeMessage(currentPersona, name, spec.hypothesis, spec.goal),
          timestamp: formatMessageTime(),
        },
      ],
    }));
  };

  const finalizeHypothesisValidator = (input: HypothesisValidatorFinalizeInput) => {
    const name = input.name.trim();
    if (!name) return;

    // Create the experiment spec
    const spec: ExperimentSpec = {
      name,
      hypothesis: input.hypothesis,
      goal: input.goal,
      channel: 'digital',
      experimentType: input.experimentTypeChoice || 'A/B',
      typeRationale: input.typeRationale || 'Auto-derived during validator step.',
      funnelStage: input.funnelStage || 'Discovery',
      metricsApproved: input.metricsApproved,
    };

    setExperimentSpecsByName((prev) => ({
      ...prev,
      [name]: spec,
    }));

    setExperiments((prev) => [...new Set([...prev, name])]);
    setSelectedExperiment(name);

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

    // Create a new thread with a brief handoff card!
    const threadId = 'thread_' + Date.now();
    const briefBody = buildBriefBody(spec, {
      'opportunity-sizing': input.opportunitySkipped ? { skipped: true } : input.opportunity,
      'metrics-tracking': { ...input.metrics, primaryMetrics: input.metrics.primaryMetricIds },
      'power-calculator': input.power,
      'experiment-type': { experimentType: input.experimentTypeChoice, typeRationale: input.typeRationale },
    });

    const handoffMessage: ChatMessage = {
      id: 'handoff_' + Date.now(),
      role: 'assistant',
      kind: 'brief-handoff',
      reportId: `report_brief_${Date.now()}`,
      briefTitle: `Experiment Brief: ${name}`,
      briefBody,
      content: 'Your digital experiment brief has been compiled.',
      timestamp: formatMessageTime(),
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
    setMessagesByThread((prev) => ({
      ...prev,
      [threadId]: [handoffMessage],
    }));

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
        summary: `Digital experiment brief for ${name}.`,
        completedAt: 'Just now',
        duration: '1.2s',
      },
    ]);

    setHypothesisValidatorOpen(false);
  };

  const selectThread = (threadId: string, experiment: string) => {
    setActiveThreadId(threadId);
    setSelectedExperiment(experiment);
  };

  const deleteThread = (threadId: string, _experiment: string) => {
    setThreadGroupState((prev) =>
      prev.map((g) => {
        if (g.experiment === _experiment) {
          return {
            ...g,
            threads: g.threads.filter((t) => t.id !== threadId),
          };
        }
        return g;
      })
    );
  };

  const deleteExperiment = (experiment: string) => {
    setExperiments((prev) => prev.filter((e) => e !== experiment));
    setThreadGroupState((prev) => prev.filter((g) => g.experiment !== experiment));
  };

  const openExperimentDataSources = (experiment: string) => {
    setExperimentDataSourcesDialogExperiment(experiment);
  };

  const closeExperimentDataSourcesDialog = () => {
    setExperimentDataSourcesDialogExperiment(null);
  };

  const updateExperimentDataSources = (experiment: string, config: ExperimentDataSourceConfig) => {
    setExperimentDataSources((prev) => ({
      ...prev,
      [experiment]: config,
    }));
  };

  const updateExperimentSpec = (experiment: string, patch: Partial<ExperimentSpec>) => {
    setExperimentSpecsByName((prev) => {
      const nextSpec = prev[experiment] ? { ...prev[experiment], ...patch } : (patch as ExperimentSpec);
      return {
        ...prev,
        [experiment]: nextSpec,
      };
    });
  };

  const markWorkflowStepComplete = (experiment: string, stepId: any) => {
    setWorkflowProgressByExperiment((prev) => {
      const prog = prev[experiment] || {};
      return {
        ...prev,
        [experiment]: {
          ...prog,
          [stepId]: true,
        },
      };
    });
  };

  const clearPendingModuleActivation = () => setPendingModuleActivation(null);

  const advanceToWorkflowStep = (moduleId: ModuleId) => {
    setActiveModuleId(moduleId);
    setLabModuleId(moduleId);
    setLabPanelView('form');
  };

  const selectModule = (moduleId: ModuleId) => {
    setActiveModuleId(moduleId);
  };

  const clearActiveModule = () => setActiveModuleId(null);

  const sendMessage = (content: string) => {
    if (!content.trim() || chatIsGenerating) return;

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
      return {
        ...prev,
        [threadId]: [...list, userMsg],
      };
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
      return {
        ...prev,
        [threadId]: [...list, assistantMsg],
      };
    });

    if (currentPersona === 'analyst') {
      const nlp = extractNlpParameters(content, selectedExperiment, activeModuleId);
      if (nlp) {
        setLabModuleId(nlp.moduleId);
        setActiveModuleId(nlp.moduleId);
        setLabPanelView('form');
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
        setMessagesByThread((prev) => {
          const list = prev[threadId] || [];
          return {
            ...prev,
            [threadId]: list.map((msg) => {
              if (msg.id === assistantMsgId) {
                return {
                  ...msg,
                  content: msg.content + chunk,
                };
              }
              return msg;
            }),
          };
        });
      },
      onToolStart: (tool, statusMsg) => {
        setChatActiveToolStatus(statusMsg);
        if (currentPersona === 'analyst') {
          const mappedModuleId = mapToolToModuleId(tool);
          if (mappedModuleId) {
            setLabModuleId(mappedModuleId);
            setActiveModuleId(mappedModuleId);
            setLabPanelView('form');
            const nlp = extractNlpParameters(content, selectedExperiment, mappedModuleId);
            if (nlp) {
              injectNlpParameters(nlp.moduleId, nlp.params, nlp.touchedFields);
            }
          }
        }
      },
      onArtifact: (artifactPayload) => {
        const card = {
          artifact_id: artifactPayload.artifact_id || `art_${Date.now()}`,
          type: artifactPayload.type || 'stat_results_card',
          title: artifactPayload.title || 'Analysis Card',
          payload: artifactPayload.payload || artifactPayload,
        };

        setMessagesByThread((prev) => {
          const list = prev[threadId] || [];
          return {
            ...prev,
            [threadId]: list.map((msg) => {
              if (msg.id === assistantMsgId) {
                const existingArtifacts = msg.artifacts || [];
                return {
                  ...msg,
                  artifacts: [...existingArtifacts, card],
                };
              }
              return msg;
            }),
          };
        });
      },
      onDone: () => {
        setChatIsGenerating(false);
        setChatActiveToolStatus(null);
      },
      onError: (err) => {
        console.error('Chat streaming error:', err);
        setChatIsGenerating(false);
        setChatActiveToolStatus(null);
        setMessagesByThread((prev) => {
          const list = prev[threadId] || [];
          return {
            ...prev,
            [threadId]: list.map((msg) => {
              if (msg.id === assistantMsgId) {
                return {
                  ...msg,
                  content: '⚠️ Unable to connect to backend AI assistant. Make sure the backend server is running.',
                };
              }
              return msg;
            }),
          };
        });
      },
    });
  };

  const appendChatMessages = (messages: TextChatMessage[]) => {
    setMessagesByThread((prev) => {
      const list = prev[activeThreadId] || [];
      return {
        ...prev,
        [activeThreadId]: [...list, ...messages],
      };
    });
  };

  const executePill = (prompt: string) => {
    sendMessage(prompt);
  };

  const scrollToMessage = (messageId: string) => {
    setHighlightedMessageId(messageId);
  };

  const selectLabModule = (moduleId: ModuleId) => {
    setLabModuleId(moduleId);
  };

  const updateModuleFormField = (moduleId: ModuleId, key: string, value: unknown) => {
    setModuleFormValuesByExperiment((prev) => {
      const expValues = prev[selectedExperiment] || {};
      const modValues = expValues[moduleId] || {};
      return {
        ...prev,
        [selectedExperiment]: {
          ...expValues,
          [moduleId]: {
            ...modValues,
            [key]: value,
          },
        },
      };
    });
  };

  const injectNlpParameters = (
    moduleId: ModuleId,
    params: Record<string, unknown>,
    touchedFields: string[]
  ) => {
    setModuleFormValuesByExperiment((prev) => {
      const expValues = prev[selectedExperiment] || {};
      const modValues = expValues[moduleId] || {};
      return {
        ...prev,
        [selectedExperiment]: {
          ...expValues,
          [moduleId]: {
            ...modValues,
            ...params,
          },
        },
      };
    });
    setHighlightedFieldKeys(touchedFields);
  };

  const getLockedModuleSnapshot = (moduleId: ModuleId) => {
    return moduleFormValuesByExperiment[selectedExperiment]?.[moduleId] ?? {};
  };

  const runModule = (
    moduleId: ModuleId,
    options?: {
      skipUserMessage?: boolean;
      userLabel?: string;
      paramOverrides?: Record<string, unknown>;
    }
  ) => {
    const params = {
      ...(moduleFormValuesByExperiment[selectedExperiment]?.[moduleId] ?? {}),
      ...(options?.paramOverrides ?? {}),
    };

    setModuleRunStatus('running');

    const runId = 'run-' + Date.now();
    const timestamp = formatMessageTime();

    const initialLogs = [
      `[INFO]  pipeline.init — Experiment "${selectedExperiment}" loaded`,
      `[INFO]  schema.validate — 14 tables verified, 0 anomalies`,
    ];

    const runMessage: ChatMessage = {
      id: `msg-${runId}`,
      role: 'assistant',
      kind: 'module-run',
      moduleId,
      runId,
      status: 'running' as const,
      logs: initialLogs,
      params,
      content: `Running simulation for ${MODULE_BY_ID[moduleId]?.label ?? moduleId}...`,
      timestamp,
    };

    setMessagesByThread((prev) => {
      const threadMsgs = prev[activeThreadId] || [];
      return {
        ...prev,
        [activeThreadId]: [...threadMsgs, runMessage],
      };
    });

    const steps = [
      `[INFO]  ${moduleId} — Module initialized with parameters: ${JSON.stringify(params)}`,
      `[SQL]   SELECT treatment, control, lift FROM exp_results WHERE exp_id = '${selectedExperiment.replace(/\s/g, '_').toLowerCase()}'`,
      `[DEBUG] cache.refresh — Insights snapshot updated`,
    ];

    let stepIdx = 0;
    const interval = setInterval(() => {
      if (stepIdx < steps.length) {
        const nextLog = steps[stepIdx];
        setMessagesByThread((prev) => {
          const threadMsgs = prev[activeThreadId] || [];
          return {
            ...prev,
            [activeThreadId]: threadMsgs.map((msg) => {
              if (msg.id === `msg-${runId}` && msg.kind === 'module-run') {
                return {
                  ...msg,
                  logs: [...msg.logs, nextLog],
                } as ChatMessage;
              }
              return msg;
            }),
          };
        });
        stepIdx++;
      } else {
        clearInterval(interval);
        const evaluation = buildModuleEvaluation(moduleId, params);
        const duration = MODULE_BY_ID[moduleId]?.mockDuration ?? '2.5s';
        const completedAt = 'Just now';

        const runRecord = {
          id: runId,
          moduleId,
          experiment: selectedExperiment,
          params,
          completedAt,
          duration,
          status: 'success' as const,
        };

        setModuleRunsByExperiment((prev) => {
          const runs = prev[selectedExperiment] || [];
          return {
            ...prev,
            [selectedExperiment]: [...runs, runRecord],
          };
        });

        setMessagesByThread((prev) => {
          const threadMsgs = prev[activeThreadId] || [];
          return {
            ...prev,
            [activeThreadId]: threadMsgs.map((msg) => {
              if (msg.id === `msg-${runId}` && msg.kind === 'module-run') {
                return {
                  ...msg,
                  status: 'success' as const,
                  duration,
                  evaluation,
                  logs: [...msg.logs, `[INFO]  ${moduleId} — Run successful in ${duration}`],
                } as ChatMessage;
              }
              return msg;
            }),
          };
        });

        const mod = MODULE_BY_ID[moduleId];
        setChatReports((prev) => [
          ...prev,
          {
            id: `report-${runId}`,
            runId,
            threadId: activeThreadId,
            experiment: selectedExperiment,
            moduleId,
            title: `${mod?.label ?? moduleId} Report`,
            summary: evaluation.summary,
            evaluation,
            completedAt,
            duration,
          },
        ]);

        if (isWorkflowStepId(moduleId)) {
          setWorkflowProgressByExperiment((prev) => {
            const prog = prev[selectedExperiment] || {};
            return {
              ...prev,
              [selectedExperiment]: {
                ...prog,
                [moduleId]: true,
              },
            };
          });
        }

        setModuleRunStatus('success');
      }
    }, 400);
  };

  const runActiveLabModule = () => {
    if (labModuleId) {
      runModule(labModuleId);
    }
  };

  const resetLabToTree = () => setLabPanelView('tree');
  const toggleAnalyticsLabCollapsed = () => setAnalyticsLabCollapsed((prev) => !prev);
  const toggleAnalyticsLabExpanded = () => setAnalyticsLabExpanded((prev) => !prev);

  const openModuleRun = (_runId: string) => {
    setLabPanelView('runs');
  };

  const openReport = (_reportId: string) => {
    setCurrentTab('reports');
  };

  const openChartDrawer = (chartId: string) => {
    setChartDrawerOpen(true);
    setChartDrawerTargetId(chartId);
  };

  const closeChartDrawer = () => {
    setChartDrawerOpen(false);
    setChartDrawerTargetId(null);
  };

  const goHome = () => {
    setCurrentTab('chat');
    setActivePhase('auto');
    setActiveModuleId(null);
    setSelectedProjectId(null);
    setActiveGlobalPage('workspace');
  };

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
        knowledgeArchiveOpen,
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
        isLlmProcessing,
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
        openKnowledgeArchive,
        closeKnowledgeArchive,
        login,
        logout,
        setPersona: setCurrentPersona,
        setTab: setCurrentTab,
        setActivePhase,
        openChartDrawer,
        closeChartDrawer,
        goHome,
        selectProject,
        openNewProjectPanel,
        closeNewProjectPanel,
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
        setLabPanelView,
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