import type { ChatMessage, Persona, ProjectChannel } from '../context/types'
import {
  INITIAL_EXPERIMENT_PROJECT_IDS,
  INITIAL_PROJECTS,
  INITIAL_THREAD_GROUPS_WITH_PROJECTS,
} from './projects'

export const EXPERIMENTS = [
  'Walmart Banner Redesign',
  'Cart Flow Optimization',
  'Holiday Promo Lift Test',
  'Dedicated Cashier Staffing Rollout',
] as const

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
  channel: ProjectChannel = 'digital',
): string {
  const hypLine = hypothesis?.trim() ? ` Hypothesis: "${hypothesis.trim()}".` : ''
  const goalLine = goal?.trim() ? ` Goal: "${goal.trim()}".` : ''
  if (persona === 'executive') {
    return `Setup complete for ${name} (${channel} MVP).${hypLine}${goalLine} Your experiment brief is ready below — open it as a report or download the markdown.`
  }
  return `Initiative Setup & Benchmarking setup is complete for "${name}" (${channel} MVP).${hypLine}${goalLine} Your brief is ready in this chat and under Reports. You can refine modules anytime in Analytics Lab.`
}

export function buildAssistantReply(persona: Persona, userMessage: string): string {
  const preview = userMessage.length > 60 ? `${userMessage.slice(0, 60)}…` : userMessage
  if (persona === 'executive') {
    return `Understood — "${preview}" I'll compile ROI, lift, and reach metrics and return a business-ready summary shortly.`
  }
  return `I've noted your request. Use the Analytics Lab panel on the right to review parameters and execute the model (Run Analytical Model or Ctrl+Enter).`
}

export type { ChatMessage }

export const MOCK_MESSAGES: ChatMessage[] = [
  {
    id: 'm1',
    role: 'user',
    content: 'What were the results of the Walmart Banner Redesign test?',
    timestamp: '10:32 AM',
  },
  {
    id: 'm2',
    role: 'assistant',
    content:
      'The Walmart Banner Redesign test showed a +4.2% lift in click-through rate with 95% confidence. Treatment group GMV increased by $1.2M over the 14-day test window.',
    timestamp: '10:32 AM',
  },
  {
    id: 'm3',
    role: 'user',
    content: 'Can you break that down by audience segment?',
    timestamp: '10:35 AM',
  },
  {
    id: 'm4',
    role: 'assistant',
    content:
      'Mobile users drove 68% of the lift (+5.8% CTR), while desktop showed a modest +1.9%. Returning customers responded strongest at +6.1% conversion lift.',
    timestamp: '10:35 AM',
  },
]

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
