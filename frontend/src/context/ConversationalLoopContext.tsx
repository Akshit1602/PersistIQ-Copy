import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { streamChatResponse, fetchExperiments, type Experiment } from '../services/api';

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
  text?: string; // Provided for backwards compatibility with legacy text references
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
  executionStatus: string | null; // Alias for activeToolStatus

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

const ConversationalLoopContext = createContext<ConversationalLoopContextType | undefined>(undefined);

export const ConversationalLoopProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
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
      onToolStart: (_tool, statusMsg) => {
        setActiveToolStatus(statusMsg);
      },
      onArtifact: (artifactPayload) => {
        const card: UIArtifactCard = {
          artifact_id: artifactPayload.artifact_id || `art_${Date.now()}`,
          type: artifactPayload.type || 'stat_results_card',
          title: artifactPayload.title || 'Analysis Card',
          payload: artifactPayload.payload || artifactPayload,
        };

        addArtifact(card);

        // Attach artifact directly to the assistant message
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