import type {
  ChatMessage,
  ModuleFormValuesByExperiment,
  ModuleId,
  Persona,
} from '../context/types'
import { isModuleRunMessage } from '../context/types'
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
  | { type: 'module-suggest'; userContent: string; moduleId: ModuleId; reply: string }
  | { type: 'llm-route'; userContent: string; reply: string }

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

// ─── Module-routing intelligence ─────────────────────────────────────────────
// Detects domain-specific queries and routes to appropriate modules.

interface ModuleRoute {
  moduleId: ModuleId
  reply: string
}

function detectFoundationRoute(text: string): ModuleRoute | null {
  const lower = text.toLowerCase()
  if (/data\s*(quality|validation|check|integrity|completeness|issue)/i.test(lower)) {
    return { moduleId: 'data-validation', reply: 'This looks like a data quality question. I\'m opening the **Data Validation** module — it can check completeness, null rates, and integrity constraints across your experiment tables.' }
  }
  if (/schema|table\s*structure|columns?\s*(available|list|what)|dimension|attribute/i.test(lower)) {
    return { moduleId: 'schema-discovery', reply: 'Opening **Schema Discovery** — this module maps your data schema, available dimensions, and joinable attributes for the experiment.' }
  }
  if (/distribution\s*(shift|drift|change)|covariate\s*shift|population\s*change/i.test(lower)) {
    return { moduleId: 'distribution-shift', reply: 'Routing to the **Distribution Shift** module — it detects pre/post changes in covariate distributions that could bias your causal estimates.' }
  }
  if (/pipeline|data\s*(freshness|lag|delay|latency|feed)/i.test(lower)) {
    return { moduleId: 'pipeline-health', reply: 'Opening **Pipeline Health** — this monitors data freshness, lag, and feed reliability for your experiment metrics.' }
  }
  if (/watchtower|anomal|outlier|spike|alert/i.test(lower)) {
    return { moduleId: 'watchtower', reply: 'Routing to **Watchtower** — it continuously monitors for anomalies, metric spikes, and data quality alerts across your store panel.' }
  }
  if (/dimension\s*setup|segment|grouping|stratif/i.test(lower)) {
    return { moduleId: 'dimension-setup', reply: 'Opening **Dimension Setup** — configure how stores are segmented and stratified for balanced experiment groups.' }
  }
  return null
}

function detectCausalRoute(text: string): ModuleRoute | null {
  const lower = text.toLowerCase()
  if (/forecast|counterfactual|predict|project(ed|ion)|what.*(would|will).*happen|future\s*(lift|sales|impact)/i.test(lower)) {
    return { moduleId: 'forecasting', reply: 'Opening the **Forecasting & Counterfactual Predictor** — select your estimator(s) and configure the flight window to generate counterfactual projections and full-fleet scale simulations.' }
  }
  if (/causal|treatment\s*effect|did\s|diff.*in.*diff|incremental\s*lift|net\s*lift|attribution|isolat.*impact/i.test(lower)) {
    return { moduleId: 'causal-did', reply: 'Routing to the **Causal Inference Engine** — configure your estimator (SDID, Staggered DiD, DML, Causal Forests, etc.) and confounder adjustments to isolate true incremental store lift.' }
  }
  if (/roi|return\s*on|money\s*waterfall|p&l|margin|cost.*benefit|payback/i.test(lower)) {
    return { moduleId: 'roi-synthesis', reply: 'Opening **ROI Synthesis (P&L Money Waterfall)** — this translates your causal lift into a full P&L breakdown including halo effects, cannibalization, and net incremental margin.' }
  }
  if (/simpson|heterogene|paradox|subgroup|segment.*effect|hte/i.test(lower)) {
    return { moduleId: 'simpsons-paradox', reply: 'Routing to **Simpson\'s Paradox & Heterogeneity Checker** — it identifies whether aggregate results mask opposing effects across store segments.' }
  }
  if (/learn|meta.*analy|prior\s*(experiment|test|result)|historical|knowledge\s*base/i.test(lower)) {
    return { moduleId: 'learnings-repository', reply: 'Opening the **Learnings & Meta-Analysis Repository** — access historical experiment results, meta-analyses, and institutional knowledge to inform your current design.' }
  }
  return null
}

function detectPreplanningRoute(text: string): ModuleRoute | null {
  const lower = text.toLowerCase()
  if (/power|sample\s*size|mde|minimum\s*detectable|how\s*many\s*(store|unit|week)/i.test(lower)) {
    return { moduleId: 'power-calculator', reply: 'Opening the **Power Calculator** — specify your MDE, significance level, and design to determine the required sample size and test duration.' }
  }
  if (/balance|covariate.*balance|match.*quality|pre.*treatment.*parity/i.test(lower)) {
    return { moduleId: 'balance-diagnostics', reply: 'Routing to **Balance Diagnostics** — check covariate balance between test and control groups before and after matching.' }
  }
  if (/opportunity|size.*opportunity|addressable|total.*impact|upside/i.test(lower)) {
    return { moduleId: 'opportunity-sizing', reply: 'Opening **Opportunity Sizing** — estimate the addressable impact and expected lift at various fleet-expansion tiers.' }
  }
  if (/metric|kpi|what.*measure|primary.*outcome|success.*criter/i.test(lower)) {
    return { moduleId: 'metrics-tracking', reply: 'Routing to **Metrics Tracking** — define your primary, secondary, and guardrail metrics for the experiment.' }
  }
  if (/experiment\s*type|ab.*test|switchback|geo.*test|cluster.*random|design/i.test(lower)) {
    return { moduleId: 'experiment-type', reply: 'Opening **Experiment Type** — choose the optimal experimental design (A/B, switchback, geo-randomized, stepped-wedge) given your constraints.' }
  }
  if (/brief|summary|spec|document|setup.*complete/i.test(lower)) {
    return { moduleId: 'brief-generator', reply: 'Routing to the **Brief Generator** — it compiles your experiment setup into a shareable specification document.' }
  }
  if (/audience|who.*target|store.*select|inclusion|exclusion|panel/i.test(lower)) {
    return { moduleId: 'audience-selection', reply: 'Opening **Audience Selection** — configure which stores enter the test and control panels based on your eligibility criteria.' }
  }
  return null
}

function detectMonitoringRoute(text: string): ModuleRoute | null {
  const lower = text.toLowerCase()
  if (/srm|sample\s*ratio|allocation.*mismatch|ratio.*check/i.test(lower)) {
    return { moduleId: 'health-monitor', reply: 'Routing to **Health Monitor** — it checks for sample ratio mismatch (SRM), allocation drift, and other integrity issues in your live experiment.' }
  }
  if (/sequential|early\s*stop|peek|interim|continuous\s*monitor/i.test(lower)) {
    return { moduleId: 'sequential-testing', reply: 'Opening **Sequential Testing** — configure always-valid confidence intervals and optional stopping boundaries for your live experiment.' }
  }
  if (/experiment.*analys|live.*result|current.*status|running.*test|in.*flight/i.test(lower)) {
    return { moduleId: 'experiment-analysis', reply: 'Routing to **Experiment Analysis** — view interim results, confidence intervals, and decision readiness for your in-flight test.' }
  }
  return null
}

function resolveModuleRoute(text: string): ModuleRoute | null {
  return detectFoundationRoute(text) ?? detectCausalRoute(text) ?? detectPreplanningRoute(text) ?? detectMonitoringRoute(text)
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
      reply: `Opening ${label} as the next Initiative Setup & Benchmarking step.`,
    }
  }

  const contextual = buildContextualReply(ctx.messages, trimmed)
  if (contextual) {
    return { type: 'contextual-run', userContent: trimmed, reply: contextual }
  }

  const nlp = extractNlpParameters(trimmed, ctx.selectedExperiment, resolveActiveModule(ctx))
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

  // Module-routing: detect domain-specific queries and suggest/open the right module
  const moduleRoute = resolveModuleRoute(trimmed)
  if (moduleRoute) {
    return {
      type: 'module-suggest',
      userContent: trimmed,
      moduleId: moduleRoute.moduleId,
      reply: moduleRoute.reply,
    }
  }

  // Fallback: route to LLM for intelligent response
  return { type: 'llm-route', userContent: trimmed, reply: buildAssistantReply(ctx.persona, trimmed) }
}
