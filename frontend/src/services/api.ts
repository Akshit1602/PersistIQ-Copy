/**
 * Empty string means same-origin, which is what Databricks Apps needs: there the
 * FastAPI process serves the built SPA and the API from one host. Local dev sets
 * VITE_API_BASE_URL in frontend/.env.local to reach the backend on its own port.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export interface Experiment {
  experiment_id: string;
  name: string;
  status: string;
  primary_metric: string;
  sample_size: number;
  srm_status: string;
}

export interface StreamChatParams {
  message: string;
  threadId?: string;
  activeExperimentId?: string | null;
  onToken: (token: string) => void;
  onToolStart: (tool: string, message: string) => void;
  onArtifact: (artifact: any) => void;
  onDone: () => void;
  onError: (error: any) => void;
}

export interface ApprovalParams {
  threadId: string;
  approved: boolean;
  userFeedback?: string;
}

/**
 * Fetch cataloged experiments for top dropdown and MatchView Hub
 */
export async function fetchExperiments(): Promise<Experiment[]> {
  const res = await fetch(`${API_BASE_URL}/api/experiments`);
  if (!res.ok) {
    throw new Error(`Failed to fetch experiments: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch projects from backend database
 */
export async function fetchProjects(): Promise<any[]> {
  const res = await fetch(`${API_BASE_URL}/api/projects`);
  if (!res.ok) {
    throw new Error(`Failed to fetch projects: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch chat thread groups from backend database
 */
export async function fetchThreads(): Promise<any[]> {
  const res = await fetch(`${API_BASE_URL}/api/projects/threads`);
  if (!res.ok) {
    throw new Error(`Failed to fetch threads: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch conversation messages for a thread from backend database
 */
export async function fetchConversationMessages(threadId: string): Promise<any[]> {
  const res = await fetch(`${API_BASE_URL}/api/projects/conversations/${threadId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch conversations for thread ${threadId}: ${res.statusText}`);
  }
  return res.json();
}

export interface InputSuggestionField {
  value: number;
  source: string;
  confidence: string;
  rationale: string;
  row_count: number;
  as_of?: string | null;
}

export interface InputSuggestionResponse {
  experiment: string;
  channel: string;
  source: string;
  as_of?: string | null;
  experiment_match?: string | null;
  fields: Record<string, InputSuggestionField>;
}

const EMPTY_SUGGESTIONS: InputSuggestionResponse = {
  experiment: '',
  channel: 'digital',
  source: 'unavailable',
  fields: {},
};

/**
 * Baselines derived from the selected experiment's own data. Resolves to an
 * empty field map on any failure: a missing profile must degrade to the app's
 * own suggestions, never break the form.
 */
export async function fetchInputSuggestions(
  experiment: string,
  channel: string,
): Promise<InputSuggestionResponse> {
  try {
    const params = new URLSearchParams({ experiment, channel });
    const res = await fetch(`${API_BASE_URL}/api/suggestions/inputs?${params}`);
    if (!res.ok) return { ...EMPTY_SUGGESTIONS, experiment, channel };
    return await res.json();
  } catch {
    return { ...EMPTY_SUGGESTIONS, experiment, channel };
  }
}

/**
 * Stream Copilot response (tokens, tool execution badges, and UI artifacts)
 */
export async function streamChatResponse({
  message,
  threadId = 'matchview_session',
  activeExperimentId = null,
  onToken,
  onToolStart,
  onArtifact,
  onDone,
  onError,
}: StreamChatParams): Promise<void> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message,
        thread_id: threadId,
        active_experiment_id: activeExperimentId,
      }),
    });

    if (!response.ok) {
      throw new Error(`Server error (${response.status}): ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('ReadableStream reader is not available in browser response.');
    }

    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || ''; // Hold onto incomplete chunk for next loop iteration

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;

        const dataStr = trimmed.replace('data: ', '').trim();
        if (dataStr === '[DONE]') {
          onDone();
          return;
        }

        try {
          const event = JSON.parse(dataStr);
          if (event.type === 'text_token' && onToken) {
            onToken(event.content);
          } else if (event.type === 'tool_start' && onToolStart) {
            onToolStart(event.tool, event.message);
          } else if (event.type === 'artifact' && onArtifact) {
            onArtifact(event.payload);
          }
        } catch (err) {
          console.error('Error parsing SSE JSON:', err, 'Raw string:', dataStr);
        }
      }
    }
    onDone();
  } catch (error) {
    console.error('Chat stream exception:', error);
    onError(error);
  }
}

/**
 * Resume an interrupted LangGraph workflow following human approval/rejection
 */
export async function resumeApproval({
  threadId,
  approved,
  userFeedback = '',
}: ApprovalParams): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/api/approval/resume`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      thread_id: threadId,
      approved,
      user_feedback: userFeedback,
    }),
  });

  if (!response.ok) {
    throw new Error(`Approval resume error: ${response.statusText}`);
  }
  return response.json();
}