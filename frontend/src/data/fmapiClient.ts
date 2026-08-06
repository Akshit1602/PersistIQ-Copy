/**
 * Client for the real Databricks Foundation Model API (FMAPI) chat endpoint.
 * Backed by server.py's /api/fmapi/chat, which uses WorkspaceClient() to
 * query a Databricks serving endpoint — genuine LLM calls, not a mock.
 *
 * Supports OpenAI-compatible tool calling: pass `tools` to enable the LLM
 * to return structured function calls instead of plain text.
 */

import type { AgentTool } from './agentTools'

export interface FmapiChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls?: FmapiToolCall[]
  tool_call_id?: string
}

export interface FmapiToolCall {
  id: string
  type: 'function'
  function: {
    name: string
    arguments: string // JSON-encoded
  }
}

export interface FmapiChatResult {
  reply: string | null
  tool_calls: FmapiToolCall[] | null
  error: string | null
  hint: string | null
}

export const FMAPI_ENDPOINTS = [
  'databricks-claude-sonnet-4-6',
  'databricks-claude-haiku-4-5',
  'databricks-claude-opus-4-6',
] as const

export type FmapiEndpoint = (typeof FMAPI_ENDPOINTS)[number]

export interface FmapiChatOptions {
  model?: FmapiEndpoint
  systemPrompt?: string
  maxTokens?: number
  tools?: AgentTool[]
  tool_choice?: 'auto' | 'none' | { type: 'function'; function: { name: string } }
}

export async function queryFmapiChat(
  messages: FmapiChatMessage[],
  options?: FmapiChatOptions,
): Promise<FmapiChatResult> {
  try {
    const res = await fetch('/api/fmapi/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages,
        model: options?.model,
        systemPrompt: options?.systemPrompt,
        maxTokens: options?.maxTokens,
        tools: options?.tools,
        tool_choice: options?.tool_choice,
      }),
    })
    const json = await res.json()
    if (!res.ok) {
      return {
        reply: null,
        tool_calls: null,
        error: json.error ?? `Request failed (${res.status})`,
        hint: json.hint ?? null,
      }
    }
    return {
      reply: json.reply ?? null,
      tool_calls: json.tool_calls ?? null,
      error: null,
      hint: null,
    }
  } catch {
    return {
      reply: null,
      tool_calls: null,
      error: 'Could not reach the model endpoint — check your connection.',
      hint: null,
    }
  }
}
