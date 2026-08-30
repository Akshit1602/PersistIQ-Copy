import type {
  ChatMessage,
  ModuleFormValuesByExperiment,
  ModuleId,
  Persona,
} from '../context/types'
import { isModuleRunMessage } from '../context/types'
import type { SuggestionContext } from './inputSuggestions'
import { buildAssistantReply } from './mock'
import {
  buildNlpSyncReply,
  extractNlpParameters,
} from './nlpParameterExtractor'
import { MODULE_BY_ID, isModuleId } from './moduleRegistry'
import { HYPOTHESIS_WORKFLOW_STEPS } from './hypothesisWorkflow'

export interface ChatRouterContext {
  persona: Persona
  activeModuleId: ModuleId | null
  labModuleId: ModuleId | null
  selectedExperiment: string
  moduleFormValuesByExperiment: ModuleFormValuesByExperiment
  messages: ChatMessage[]
  activeDomain?: 'ecomm' | 'store'
  /** Lets parameters parsed from chat fall back to data-derived suggestions. */
  suggestionContext?: SuggestionContext
}

export function isStoreDomainQuery(text: string): boolean {
  return /kiosk|endcap|foot\s*traffic|register|dwell\s*time|pos|aisle|store\s*cluster|cluster/i.test(text)
}

export type ChatIntent =
  | { type: 'text-reply'; userContent: string; reply: string }
  | {
      type: 'nlp-inject'
      moduleId: ModuleId
      params: Record<string, unknown>
      touchedFields: string[]
      autoFilledFields: string[]
      userContent: string
      reply: string
    }
  | { type: 'open-insights'; userContent: string; reply: string }
  | { type: 'contextual-run'; userContent: string; reply: string }
  | { type: 'advance-workflow'; userContent: string; moduleId: ModuleId; reply: string }

function resolveActiveModule(ctx: ChatRouterContext): ModuleId | null {
  return ctx.labModuleId ?? ctx.activeModuleId
}

function getLastRunMessage(messages: ChatMessage[]) {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i]
    if (isModuleRunMessage(msg)) return msg
  }
  return null
}

function isInsightsIntent(text: string): boolean {
  return /(show|open|view)\s+(the\s+)?(results?|insights?|charts?|workspace)/i.test(text)
}

function resolveProceedIntent(text: string): ModuleId | null {
  const lower = text.toLowerCase()
  if (!/proceed\s+to|go\s+to\s+(metrics|audience|power|brief|opportunity|experiment)|next\s+step/.test(lower)) {
    return null
  }

  for (const step of HYPOTHESIS_WORKFLOW_STEPS) {
    if (lower.includes(step.label.toLowerCase()) || lower.includes(step.id.replace(/-/g, ' '))) {
      return step.moduleId
    }
  }
  if (/metrics/.test(lower)) return 'metrics-tracking'
  if (/experiment\s*type/.test(lower)) return 'experiment-type'
  if (/power/.test(lower)) return 'power-calculator'
  if (/audience/.test(lower)) return 'audience-selection'
  if (/brief/.test(lower)) return 'brief-generator'
  if (/opportun|siz/.test(lower)) return 'opportunity-sizing'
  return null
}

function buildContextualReply(messages: ChatMessage[], userContent: string): string | null {
  const lastRun = getLastRunMessage(messages)
  if (!lastRun) return null

  const mod = MODULE_BY_ID[lastRun.moduleId]
  const lower = userContent.toLowerCase()

  if (/srm|allocation|drift|warn/i.test(lower)) {
    const warnLine = lastRun.logs.find((l) => l.includes('[WARN]'))
    return warnLine
      ? `The SRM warning in the last ${mod.label} run came from minor allocation drift: ${warnLine.replace(/^\[WARN\]\s*/, '')}. Adjust parameters in the Analytics Lab if you want to re-execute.`
      : `The last ${mod.label} run completed without SRM warnings.`
  }

  if (/result|outcome|summary|what happened|sample\s*size/i.test(lower)) {
    if (lastRun.evaluation?.summary) return lastRun.evaluation.summary
    return lastRun.status === 'success'
      ? `${mod.label} finished in ${lastRun.duration ?? 'the last run'}. Open Insights for the full analytical workspace.`
      : `${mod.label} is still ${lastRun.status === 'running' ? 'executing' : 'in an error state'}.`
  }

  return null
}

export function resolveChatIntent(content: string, ctx: ChatRouterContext): ChatIntent {
  const trimmed = content.trim()
  if (!trimmed) {
    return { type: 'text-reply', userContent: trimmed, reply: '' }
  }

  if (ctx.persona === 'executive') {
    return { type: 'text-reply', userContent: trimmed, reply: buildAssistantReply(ctx.persona, trimmed) }
  }

  if (isInsightsIntent(trimmed)) {
    return {
      type: 'open-insights',
      userContent: trimmed,
      reply: 'Opening the dedicated Insights workspace with your latest analytical outputs.',
    }
  }

  const proceedModule = resolveProceedIntent(trimmed)
  if (proceedModule && isModuleId(proceedModule)) {
    const label = MODULE_BY_ID[proceedModule].label
    return {
      type: 'advance-workflow',
      userContent: trimmed,
      moduleId: proceedModule,
      reply: `Opening ${label} as the next Hypothesis Validator step.`,
    }
  }

  const contextual = buildContextualReply(ctx.messages, trimmed)
  if (contextual) {
    return { type: 'contextual-run', userContent: trimmed, reply: contextual }
  }

  const nlp = extractNlpParameters(
    trimmed,
    ctx.selectedExperiment,
    resolveActiveModule(ctx),
    ctx.suggestionContext,
  )
  if (nlp) {
    return {
      type: 'nlp-inject',
      moduleId: nlp.moduleId,
      params: nlp.params,
      touchedFields: nlp.touchedFields,
      autoFilledFields: nlp.autoFilledFields,
      userContent: trimmed,
      reply: buildNlpSyncReply(nlp.moduleId, nlp.touchedFields, nlp.autoFilledFields),
    }
  }

  return { type: 'text-reply', userContent: trimmed, reply: buildAssistantReply(ctx.persona, trimmed) }
}
