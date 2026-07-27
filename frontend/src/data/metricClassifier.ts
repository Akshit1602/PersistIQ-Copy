export type FunnelStage =
  | 'acquisition'
  | 'activation'
  | 'retention'
  | 'monetization'
  | 'engagement'

export type MetricDirection = 'increase' | 'decrease'

export type DerivedExperimentType = 'A/B' | 'A/B/C' | 'Causal'

export interface MetricSuggestion {
  name: string
  rationale: string
  direction: MetricDirection
}

export interface MetricSelection {
  name: string
  direction: MetricDirection
}

export interface MetricClassificationResult {
  funnelStage: FunnelStage
  funnelRationale: string
  primary: MetricSuggestion[]
  secondary: MetricSuggestion[]
  guardrail: MetricSuggestion[]
  experimentType: DerivedExperimentType
  typeRationale: string
}

const DECREASE_METRICS =
  /bounce|refund|abandon|churn|unsubscribe|error|crash|ticket|complaint|latency/i

export function inferMetricDirection(name: string): MetricDirection {
  return DECREASE_METRICS.test(name) ? 'decrease' : 'increase'
}

const STAGE_KEYWORDS: { stage: FunnelStage; patterns: RegExp[] }[] = [
  {
    stage: 'acquisition',
    patterns: [/acquisit/i, /traffic/i, /click[- ]?through|ctr/i, /banner/i, /ad\b/i, /impress/i],
  },
  {
    stage: 'activation',
    patterns: [/activat/i, /signup|sign[- ]?up/i, /onboard/i, /first\s+(order|purchase)/i],
  },
  {
    stage: 'retention',
    patterns: [/retent/i, /repeat/i, /churn/i, /return\s+visit/i, /loyalty/i],
  },
  {
    stage: 'monetization',
    patterns: [/gmv|revenue|aov|average\s+order|conversion|cvr|checkout|cart|purchase|promo/i],
  },
  {
    stage: 'engagement',
    patterns: [/engag/i, /time\s+on\s+(site|app)/i, /session/i, /dwell/i],
  },
]

function withDirection(
  items: { name: string; rationale: string }[],
): MetricSuggestion[] {
  return items.map((m) => ({ ...m, direction: inferMetricDirection(m.name) }))
}

const STAGE_METRICS: Record<
  FunnelStage,
  { primary: MetricSuggestion[]; secondary: MetricSuggestion[]; guardrail: MetricSuggestion[] }
> = {
  acquisition: {
    primary: withDirection([
      { name: 'CTR', rationale: 'Direct signal that the creative change improves click propensity.' },
    ]),
    secondary: withDirection([
      {
        name: 'Landing CVR',
        rationale: 'Downstream quality of acquired traffic after the click.',
      },
    ]),
    guardrail: withDirection([
      {
        name: 'Bounce Rate',
        rationale: 'Must not rise — protects against clickbait or mismatched landing experiences.',
      },
    ]),
  },
  activation: {
    primary: withDirection([
      {
        name: 'Signup Completion Rate',
        rationale: 'Core activation success metric for the hypothesized change.',
      },
    ]),
    secondary: withDirection([
      {
        name: 'Time-to-First-Action',
        rationale: 'Captures friction reduction after signup.',
      },
    ]),
    guardrail: withDirection([
      {
        name: 'Support Ticket Rate',
        rationale: 'Must not increase if the flow confuses new users.',
      },
    ]),
  },
  retention: {
    primary: withDirection([
      {
        name: '7-Day Return Rate',
        rationale: 'Primary retention indicator for the proposed change.',
      },
    ]),
    secondary: withDirection([
      {
        name: 'Orders per Returning User',
        rationale: 'Downstream value of retained users.',
      },
    ]),
    guardrail: withDirection([
      {
        name: 'Unsubscribe Rate',
        rationale: 'Must not worsen if messaging frequency or tone changes.',
      },
    ]),
  },
  monetization: {
    primary: withDirection([
      {
        name: 'Conversion Rate (CVR)',
        rationale: 'Primary success indicator for checkout / cart / promo hypotheses.',
      },
    ]),
    secondary: withDirection([
      { name: 'AOV', rationale: 'Downstream revenue quality beyond conversion count.' },
      {
        name: 'GMV per Visitor',
        rationale: 'Combines conversion and basket size for commercial impact.',
      },
    ]),
    guardrail: withDirection([
      {
        name: 'Refund Rate',
        rationale: 'Must not decline in quality — protects margin and trust.',
      },
      {
        name: 'Cart Abandonment',
        rationale: 'Must not increase if the change adds friction.',
      },
    ]),
  },
  engagement: {
    primary: withDirection([
      { name: 'Sessions per User', rationale: 'Primary engagement depth metric.' },
    ]),
    secondary: withDirection([
      {
        name: 'Pages per Session',
        rationale: 'Secondary signal of content / UX engagement.',
      },
    ]),
    guardrail: withDirection([
      {
        name: 'Crash / Error Rate',
        rationale: 'Must not rise if the change introduces technical risk.',
      },
    ]),
  },
}

export function detectFunnelStage(text: string): { stage: FunnelStage; rationale: string } {
  for (const entry of STAGE_KEYWORDS) {
    if (entry.patterns.some((p) => p.test(text))) {
      return {
        stage: entry.stage,
        rationale: `Hypothesis/goal language maps most strongly to the ${entry.stage} funnel stage.`,
      }
    }
  }
  return {
    stage: 'monetization',
    rationale:
      'No stronger funnel keyword matched; defaulting to monetization (CVR/GMV) as the digital MVP default.',
  }
}

export function deriveExperimentType(input: {
  hypothesis: string
  goal: string
  funnelStage?: FunnelStage
  addressableVolume?: number
  currentInteractionRate?: number
  targetInteractionRate?: number
}): { experimentType: DerivedExperimentType; typeRationale: string } {
  const combined = `${input.hypothesis} ${input.goal}`.trim()
  const liftGap =
    input.targetInteractionRate !== undefined && input.currentInteractionRate !== undefined
      ? input.targetInteractionRate - input.currentInteractionRate
      : undefined

  if (
    /causal|difference[- ]in[- ]difference|did\b|before\s*\/\s*after|geo\s*test|rollout|quasi[- ]?experiment/i.test(
      combined,
    )
  ) {
    return {
      experimentType: 'Causal',
      typeRationale:
        'Hypothesis language points to observational or rollout-style change — Causal inference is recommended over a classic randomized split.',
    }
  }

  const wantsMulti =
    /a\/b\/c|three\s+variant|multi[- ]?variant|several\s+variant|compare\s+multiple/i.test(
      combined,
    ) ||
    (liftGap !== undefined && liftGap >= 4) ||
    (input.addressableVolume !== undefined && input.addressableVolume >= 500000)

  if (wantsMulti) {
    return {
      experimentType: 'A/B/C',
      typeRationale:
        'Volume or lift ambition supports comparing multiple treatments — A/B/C is the recommended digital design.',
    }
  }

  return {
    experimentType: 'A/B',
    typeRationale: `Single digital change on the ${input.funnelStage ?? 'primary'} funnel stage with moderate impact — classic A/B is the most efficient design.`,
  }
}

/** Deterministic mock classifier — replaceable by Akshit’s LLM with the same return shape. */
export function classifyHypothesisMetrics(
  hypothesis: string,
  goal: string,
  options?: {
    expectedLift?: number
    funnelStage?: FunnelStage
    addressableVolume?: number
    currentInteractionRate?: number
    targetInteractionRate?: number
  },
): MetricClassificationResult {
  const combined = `${hypothesis} ${goal}`.trim()
  const detected = detectFunnelStage(combined || 'conversion checkout')
  const stage = options?.funnelStage ?? detected.stage
  const buckets = STAGE_METRICS[stage]
  const { experimentType, typeRationale } = deriveExperimentType({
    hypothesis,
    goal,
    funnelStage: stage,
    addressableVolume: options?.addressableVolume,
    currentInteractionRate: options?.currentInteractionRate,
    targetInteractionRate: options?.targetInteractionRate,
  })

  return {
    funnelStage: stage,
    funnelRationale: options?.funnelStage
      ? `Funnel impact stage set to ${stage} from opportunity sizing.`
      : detected.rationale,
    primary: buckets.primary,
    secondary: buckets.secondary,
    guardrail: buckets.guardrail,
    experimentType,
    typeRationale,
  }
}

export function formatMetricList(suggestions: MetricSuggestion[] | MetricSelection[]): string {
  return suggestions.map((s) => s.name).join(', ')
}

export function formatMetricRationales(suggestions: MetricSuggestion[]): string {
  return suggestions.map((s) => `${s.name}: ${s.rationale}`).join('\n')
}

export function formatMetricDirections(selections: MetricSelection[]): string {
  return selections
    .map((s) => `${s.name} (Expected Trend: ${s.direction === 'increase' ? 'Increase' : 'Decrease'})`)
    .join(', ')
}
