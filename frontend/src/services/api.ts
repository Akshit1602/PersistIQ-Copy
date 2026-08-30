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

export interface LoadedDatasetColumn {
  name: string;
  type: string;
  null_count: number;
  unique_count: number;
  min?: number | string;
  max?: number | string;
  avg?: number | string;
}

export interface LoadedDataset {
  table_name: string;
  total_rows: number;
  column_count: number;
  columns: LoadedDatasetColumn[];
  sample_data: Record<string, any>[];
}

export interface ApiProject {
  id: string;
  name: string;
  channel: string;
  description: string;
  experiments_count: number;
  total_records: number;
  threads_count: number;
  updated_at: string;
}

export interface ApiThreadGroup {
  id: string;
  project_id: string;
  title: string;
  channel: string;
  updated_at: string;
}

export interface ApiChatMessage {
  id: string;
  thread_id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export async function fetchExperiments(): Promise<Experiment[]> {
  const res = await fetch(`${API_BASE_URL}/api/experiments`);
  if (!res.ok) {
    throw new Error(`Failed to fetch experiments: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchLoadedDatasets(table?: string): Promise<{ tables_count: number; datasets: LoadedDataset[] }> {
  const url = table ? `${API_BASE_URL}/api/datasets?table=${encodeURIComponent(table)}` : `${API_BASE_URL}/api/datasets`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch loaded datasets: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchApiProjects(): Promise<ApiProject[]> {
  const res = await fetch(`${API_BASE_URL}/api/projects`);
  if (!res.ok) {
    throw new Error(`Failed to fetch projects: ${res.statusText}`);
  }
  const data = await res.json();
  return data.projects || [];
}

export async function fetchApiThreadGroups(projectId?: string): Promise<ApiThreadGroup[]> {
  const url = projectId ? `${API_BASE_URL}/api/projects/threads?project_id=${encodeURIComponent(projectId)}` : `${API_BASE_URL}/api/projects/threads`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch thread groups: ${res.statusText}`);
  }
  const data = await res.json();
  return data.threads || [];
}

export async function fetchThreadMessages(threadId: string): Promise<ApiChatMessage[]> {
  const res = await fetch(`${API_BASE_URL}/api/projects/threads/${encodeURIComponent(threadId)}/messages`);
  if (!res.ok) {
    throw new Error(`Failed to fetch thread messages: ${res.statusText}`);
  }
  const data = await res.json();
  return data.messages || [];
}

export async function postThreadMessage(threadId: string, role: string, content: string): Promise<ApiChatMessage> {
  const res = await fetch(`${API_BASE_URL}/api/projects/threads/${encodeURIComponent(threadId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, content }),
  });
  if (!res.ok) {
    throw new Error(`Failed to post message: ${res.statusText}`);
  }
  const data = await res.json();
  return data.message;
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
      buffer = lines.pop() || '';

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
