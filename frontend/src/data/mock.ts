import type { ChatMessage, Persona } from '../context/types'
import {
  INITIAL_EXPERIMENT_PROJECT_IDS,
  INITIAL_PROJECTS,
  INITIAL_THREAD_GROUPS_WITH_PROJECTS,
} from './projects'

export const EXPERIMENTS: string[] = []

export {
  INITIAL_PROJECTS,
  INITIAL_EXPERIMENT_PROJECT_IDS,
  INITIAL_THREAD_GROUPS_WITH_PROJECTS,
}

export const THREAD_GROUPS = INITIAL_THREAD_GROUPS_WITH_PROJECTS

export {
  EXECUTIVE_PHASES,
  buildAnalystPhaseOptions,
  PHASE_LABELS,
  getActionPills,
} from './moduleRegistry'
export type { PhaseOption, ActionPill } from './moduleRegistry'

export const INITIAL_EXPERIMENTS = [...EXPERIMENTS]

export const INITIAL_THREAD_GROUPS = INITIAL_THREAD_GROUPS_WITH_PROJECTS

export const INITIAL_ACTIVE_THREAD_ID = 't1'

export function buildInitialMessages(): Record<string, ChatMessage[]> {
  return { t1: MOCK_MESSAGES }
}

export function formatMessageTime(date = new Date()): string {
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function buildWelcomeMessage(
  persona: Persona,
  name: string,
  hypothesis?: string,
  goal?: string,
): string {
  const hypLine = hypothesis?.trim() ? ` Hypothesis: "${hypothesis.trim()}".` : ''
  const goalLine = goal?.trim() ? ` Goal: "${goal.trim()}".` : ''
  if (persona === 'executive') {
    return `Setup complete for ${name} (digital MVP).${hypLine}${goalLine} Your experiment brief is ready below — open it as a report or download the markdown.`
  }
  return `Hypothesis Validator setup is complete for "${name}" (digital MVP).${hypLine}${goalLine} Your brief is ready in this chat and under Reports. You can refine modules anytime in Analytics Lab.`
}

export function buildAssistantReply(persona: Persona, userMessage: string): string {
  const preview = userMessage.length > 60 ? `${userMessage.slice(0, 60)}…` : userMessage
  if (persona === 'executive') {
    return `Understood — "${preview}" I'll compile ROI, lift, and reach metrics and return a business-ready summary shortly.`
  }
  return `I've noted your request. Use the Analytics Lab panel on the right to review parameters and execute the model (Run Analytical Model or Ctrl+Enter).`
}

export type { ChatMessage }

export const MOCK_MESSAGES: ChatMessage[] = []

export interface ChartData {
  id: string
  title: string
  subtitle: string
  metric: string
  change: string
  positive: boolean
}

export const MOCK_CHARTS: ChartData[] = [
  {
    id: 'chart-lift',
    title: 'Conversion Lift Curve',
    subtitle: 'Treatment vs Control over 14 days',
    metric: '+4.2%',
    change: 'vs baseline',
    positive: true,
  },
  {
    id: 'chart-funnel',
    title: 'Funnel Performance',
    subtitle: 'Click → Cart → Purchase',
    metric: '12.8%',
    change: 'overall CVR',
    positive: true,
  },
  {
    id: 'chart-roi',
    title: 'ROI Projection',
    subtitle: 'Projected annual impact',
    metric: '$4.8M',
    change: 'estimated GMV',
    positive: true,
  },
  {
    id: 'chart-reach',
    title: 'Audience Reach',
    subtitle: 'Unique impressions served',
    metric: '2.4M',
    change: 'users reached',
    positive: true,
  },
]

export const CONSOLE_LOGS = [
  '[INFO]  pipeline.init — Experiment "Walmart Banner Redesign" loaded',
  '[INFO]  schema.validate — 14 tables verified, 0 anomalies',
  '[WARN]  srm.check — Minor allocation drift detected (δ=0.003)',
  '[INFO]  causal.did — Treatment effect: +0.042 (p=0.003)',
  '[INFO]  opportunity-sizing — Opportunity Sizing ran successfully in 4.56s',
  '[SQL]   SELECT treatment, control, lift FROM exp_results WHERE exp_id = \'walmart_banner\'',
  '[DEBUG] cache.refresh — Insights dashboard snapshot updated',
  '[INFO]  health.monitor — All pipelines operational',
]
