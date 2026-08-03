import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { streamChatResponse, fetchExperiments, type Experiment } from '../services/api';
import { useMatchView } from './MatchViewContext';
import type { ModuleId } from './types';
import type {
  ActiveModuleContext,
  InterviewPhase,
  InterviewPill,
  ConversationalLoopContextValue,
} from './conversationalLoopTypes';

import {
  bootstrapModuleParams,
  buildAutoFillSummary,
  buildReadyMessage,
  getNextInterviewStep,
  getSmartPillsForPhase,
} from '../data/moduleInterviewEngine';
import { MODULE_BY_ID } from '../data/moduleRegistry';
import { extractNlpParameters } from '../data/nlpParameterExtractor';
import { mapToolToModuleId } from './MatchViewContext';

export type PhaseType = 'DISCOVERY' | 'PLANNING' | 'EXECUTION' | 'EVALUATION' | 'INSIGHTS';

export interface ToolExecution {
  tool: string;
  message: string;
  status: 'running' | 'completed' | 'failed';
}

export interface UIArtifactCard {
  artifact_id: string;
  type: string;
  title: string;
  payload: Record<string, any>;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  content: string;
  text?: string;
  timestamp: string;
  phase?: PhaseType;
  executionStatus?: string | null;
  artifacts?: UIArtifactCard[];
  toolsRan?: ToolExecution[];
}

export interface ConversationalLoopContextType {
  // Chat state
  messages: ChatMessage[];
  isGenerating: boolean;
  activeToolStatus: string | null;
  executionStatus: string | null;

  // Artifacts & Cards
  artifacts: UIArtifactCard[];
  activeArtifact: UIArtifactCard | null;
  setActiveArtifact: (artifact: UIArtifactCard | null) => void;
  addArtifact: (artifact: UIArtifactCard) => void;

  // Experiment state & Lifecycle
  experiments: Experiment[];
  selectedExperimentId: string | null;
  setSelectedExperimentId: (id: string | null) => void;
  activePhase: PhaseType;
  setActivePhase: (phase: PhaseType) => void;

  // Actions
  sendMessage: (text: string) => Promise<void>;
  clearHistory: () => void;
}

export type CombinedConversationalLoopContextType = ConversationalLoopContextType & ConversationalLoopContextValue;

const ConversationalLoopContext = createContext<CombinedConversationalLoopContextType | undefined>(undefined);

export const ConversationalLoopProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const matchView = useMatchView();

  // Custom Streaming Chat states
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'msg_welcome',
      sender: 'assistant',
      content: 'Welcome to Continum MatchView Copilot! Select an experiment above or ask me to perform power calculations, SRM checks, or hypothesis tests.',
      text: 'Welcome to Continum MatchView Copilot! Select an experiment above or ask me to perform power calculations, SRM checks, or hypothesis tests.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'DISCOVERY',
    },
  ]);

  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [activeToolStatus, setActiveToolStatus] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<UIArtifactCard[]>([]);
  const [activeArtifact, setActiveArtifact] = useState<UIArtifactCard | null>(null);

  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | null>(null);
  const [activePhase, setActivePhase] = useState<PhaseType>('DISCOVERY');

  // Interview state machine states
  const [activeModuleContext, setActiveModuleContext] = useState<ActiveModuleContext | null>(null);
  const [interviewPhase, setInterviewPhase] = useState<InterviewPhase>('idle');
  const [pendingFieldKey, setPendingFieldKey] = useState<string | null>(null);
  const [confirmedFieldKeys, setConfirmedFieldKeys] = useState<string[]>([]);
  const [smartPills, setSmartPills] = useState<InterviewPill[]>([]);

  // Fetch experiments catalog on initial load
  useEffect(() => {
    fetchExperiments()
      .then((data) => {
        setExperiments(data);
        if (data && data.length > 0) {
          setSelectedExperimentId(data[0].experiment_id);
        }
      })
      .catch((err) => {
        console.warn('Backend server not connected yet or experiments fetch failed:', err);
      });
  }, []);

  const addArtifact = (artifact: UIArtifactCard) => {
    setArtifacts((prev) => {
      const exists = prev.some((a) => a.artifact_id === artifact.artifact_id);
      if (exists) return prev;
      return [...prev, artifact];
    });
    setActiveArtifact(artifact);
  };

  const sendMessage = async (userText: string) => {
    if (!userText.trim() || isGenerating) return;

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      sender: 'user',
      content: userText,
      text: userText,
      timestamp: timeStr,
      phase: activePhase,
    };

    const assistantMsgId = `assistant_${Date.now()}`;
    const assistantPlaceholder: ChatMessage = {
      id: assistantMsgId,
      sender: 'assistant',
      content: '',
      text: '',
      timestamp: timeStr,
      phase: activePhase,
      artifacts: [],
    };

    if (matchView.currentPersona === 'analyst') {
      const nlp = extractNlpParameters(userText, matchView.selectedExperiment, matchView.activeModuleId);
      if (nlp) {
        matchView.selectLabModule(nlp.moduleId);
        matchView.selectModule(nlp.moduleId);
        matchView.setLabPanelView('form');
        matchView.injectNlpParameters(nlp.moduleId, nlp.params, nlp.touchedFields);
      }
    }

    setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);
    setIsGenerating(true);
    setActiveToolStatus('Analyzing request...');

    await streamChatResponse({
      message: userText,
      threadId: 'matchview_session',
      activeExperimentId: selectedExperimentId,
      onToken: (chunk) => {
        setActiveToolStatus(null);
        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.id === assistantMsgId) {
              const updatedContent = msg.content + chunk;
              return {
                ...msg,
                content: updatedContent,
                text: updatedContent,
              };
            }
            return msg;
          })
        );
      },
      onToolStart: (tool, statusMsg) => {
        setActiveToolStatus(statusMsg);
        if (matchView.currentPersona === 'analyst') {
          const mappedModuleId = mapToolToModuleId(tool);
          if (mappedModuleId) {
            matchView.selectLabModule(mappedModuleId);
            matchView.selectModule(mappedModuleId);
            matchView.setLabPanelView('form');
            const nlp = extractNlpParameters(userText, matchView.selectedExperiment, mappedModuleId);
            if (nlp) {
              matchView.injectNlpParameters(nlp.moduleId, nlp.params, nlp.touchedFields);
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

        addArtifact(card);

        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.id === assistantMsgId) {
              const currentArtifacts = msg.artifacts || [];
              return {
                ...msg,
                artifacts: [...currentArtifacts, card],
              };
            }
            return msg;
          })
        );
      },
      onDone: () => {
        setIsGenerating(false);
        setActiveToolStatus(null);
      },
      onError: (err) => {
        console.error('Chat stream error:', err);
        setIsGenerating(false);
        setActiveToolStatus(null);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  content: '⚠️ Unable to reach Continum backend. Ensure Python server is running on http://localhost:8000.',
                  text: '⚠️ Unable to reach Continum backend. Ensure Python server is running on http://localhost:8000.',
                }
              : msg
          )
        );
      },
    });
  };

  const clearHistory = () => {
    setMessages([]);
    setArtifacts([]);
    setActiveArtifact(null);
  };

  // Interview state machine actions
  const activateModuleContext = (moduleId: ModuleId) => {
    const existingParams = matchView.getLockedModuleSnapshot(moduleId);
    const { params, autoFilledFields } = bootstrapModuleParams(
      moduleId,
      matchView.selectedExperiment,
      existingParams
    );

    const context: ActiveModuleContext = {
      moduleId,
      label: MODULE_BY_ID[moduleId]?.label ?? moduleId,
      startedAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setActiveModuleContext(context);
    setConfirmedFieldKeys(autoFilledFields);

    // Save defaults back
    Object.entries(params).forEach(([k, v]) => {
      matchView.updateModuleFormField(moduleId, k, v);
    });

    const nextStep = getNextInterviewStep(moduleId, autoFilledFields);

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (nextStep) {
      setInterviewPhase('interviewing');
      setPendingFieldKey(nextStep.fieldKey);
      setSmartPills(getSmartPillsForPhase(moduleId, autoFilledFields, 'interviewing'));

      const greeting = buildAutoFillSummary(moduleId, matchView.selectedExperiment, autoFilledFields, params);

      setMessages((prev) => [
        ...prev,
        {
          id: `system_${Date.now()}`,
          sender: 'system',
          content: greeting,
          timestamp: timeStr,
        },
        {
          id: `asst_q_${Date.now()}`,
          sender: 'assistant',
          content: nextStep.question,
          timestamp: timeStr,
        },
      ]);
    } else {
      setInterviewPhase('ready');
      setPendingFieldKey(null);
      setSmartPills(getSmartPillsForPhase(moduleId, autoFilledFields, 'ready'));

      const readyMsg = buildReadyMessage(moduleId);

      setMessages((prev) => [
        ...prev,
        {
          id: `asst_r_${Date.now()}`,
          sender: 'assistant',
          content: readyMsg,
          timestamp: timeStr,
        },
      ]);
    }

    matchView.selectLabModule(moduleId);
    matchView.setLabPanelView('form');
  };

  const submitInterviewAnswer = (fieldKey: string, value: unknown, label?: string) => {
    if (!activeModuleContext) return;

    const moduleId = activeModuleContext.moduleId;
    const updatedConfirmed = [...confirmedFieldKeys, fieldKey];
    setConfirmedFieldKeys(updatedConfirmed);

    matchView.updateModuleFormField(moduleId, fieldKey, value);

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userDisplay = label || String(value);

    // Add user's answer message
    const userMsg: ChatMessage = {
      id: `user_ans_${Date.now()}`,
      sender: 'user',
      content: userDisplay,
      timestamp: timeStr,
    };

    const nextStep = getNextInterviewStep(moduleId, updatedConfirmed);

    if (nextStep) {
      setPendingFieldKey(nextStep.fieldKey);
      setSmartPills(getSmartPillsForPhase(moduleId, updatedConfirmed, 'interviewing'));

      setMessages((prev) => [
        ...prev,
        userMsg,
        {
          id: `asst_q_${Date.now()}`,
          sender: 'assistant',
          content: nextStep.question,
          timestamp: timeStr,
        },
      ]);
    } else {
      setInterviewPhase('ready');
      setPendingFieldKey(null);
      setSmartPills(getSmartPillsForPhase(moduleId, updatedConfirmed, 'ready'));

      const readyMsg = buildReadyMessage(moduleId);

      setMessages((prev) => [
        ...prev,
        userMsg,
        {
          id: `asst_r_${Date.now()}`,
          sender: 'assistant',
          content: readyMsg,
          timestamp: timeStr,
        },
      ]);
    }
  };

  const executeSimulation = () => {
    if (!activeModuleContext) return;

    setInterviewPhase('running');
    setSmartPills([]);

    const moduleId = activeModuleContext.moduleId;
    matchView.runModule(moduleId, { skipUserMessage: true });

    // Wait and complete the interview
    setTimeout(() => {
      setInterviewPhase('complete');
      setSmartPills(getSmartPillsForPhase(moduleId, confirmedFieldKeys, 'complete'));

      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      setMessages((prev) => [
        ...prev,
        {
          id: `asst_done_${Date.now()}`,
          sender: 'assistant',
          content: `✅ Simulation for ${MODULE_BY_ID[moduleId]?.label || moduleId} run successfully. Results are compiled and visible in the Reports tab.`,
          timestamp: timeStr,
        },
      ]);
    }, 1800);
  };

  const pushResultsToInsights = () => {
    matchView.setTab('insights');
  };

  return (
    <ConversationalLoopContext.Provider
      value={{
        messages,
        isGenerating,
        activeToolStatus,
        executionStatus: activeToolStatus,
        artifacts,
        activeArtifact,
        setActiveArtifact,
        addArtifact,
        experiments,
        selectedExperimentId,
        setSelectedExperimentId,
        activePhase,
        setActivePhase,
        sendMessage,
        clearHistory,

        // Interview machine
        activeModuleContext,
        interviewPhase,
        pendingFieldKey,
        confirmedFieldKeys,
        smartPills,
        activateModuleContext,
        submitInterviewAnswer,
        executeSimulation,
        pushResultsToInsights,
      }}
    >
      {children}
    </ConversationalLoopContext.Provider>
  );
};

export const useConversationalLoop = () => {
  const context = useContext(ConversationalLoopContext);
  if (!context) {
    throw new Error('useConversationalLoop must be used within a ConversationalLoopProvider');
  }
  return context;
};