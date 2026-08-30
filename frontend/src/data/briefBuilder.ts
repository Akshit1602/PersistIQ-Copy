import type { ExperimentSpec, ExperimentTypeChoice } from '../context/types'
import type { FunnelStage } from './metricClassifier'
import { classifyHypothesisMetrics } from './metricClassifier'
import { METRIC_KPI_BY_ID } from './metricCatalog'

function formatMetricList(value: unknown): string {
  if (Array.isArray(value) && value.length > 0) {
    return value.map(String).join(', ')
  }
  return '—'
}

function formatMetricInputLines(value: unknown): string[] {
  if (!value || typeof value !== 'object') return []
  const inputs = value as Record<string, Record<string, string>>
  const lines: string[] = []
  for (const [kpiId, fields] of Object.entries(inputs)) {
    const label = METRIC_KPI_BY_ID[kpiId]?.label ?? kpiId
    const parts = Object.entries(fields)
      .filter(([, v]) => String(v).trim())
      .map(([k, v]) => `${k}: ${v}`)
    if (parts.length > 0) lines.push(`- ${label} inputs: ${parts.join('; ')}`)
  }
  return lines
}

export function buildBriefBody(
  spec: ExperimentSpec,
  moduleSnapshots: Partial<Record<string, Record<string, unknown>>>,
): string {
  const sizing = moduleSnapshots['opportunity-sizing'] ?? {}
  const metrics = moduleSnapshots['metrics-tracking'] ?? {}
  const type = moduleSnapshots['experiment-type'] ?? {}
  const power = moduleSnapshots['power-calculator'] ?? {}
  const audience = moduleSnapshots['audience-selection'] ?? {}
  const opportunitySkipped = sizing.skipped === true
  const experimentType =
    (type.experimentType as string | undefined) ??
    spec.experimentType ??
    '—'
  const typeRationale =
    (type.typeRationale as string | undefined) ?? spec.typeRationale ?? '—'

  const opportunityLines = opportunitySkipped
    ? ['- Opportunity sizing: skipped (configure later in Analytics Lab if needed)']
    : [
        `- Monthly inquiries: ${sizing.monthlyInquiries ?? '—'}`,
        `- Current IOR: ${sizing.currentIor ?? '—'}`,
        `- Target IOR: ${sizing.targetIor ?? '—'}`,
        `- Average order value: $${sizing.aov ?? '—'}`,
        `- Gross margin: ${sizing.grossMargin ?? '—'}`,
        `- Time horizon: ${sizing.timeHorizonMonths ?? '—'} months`,
      ]

  const audienceConfigured =
    audience.segment !== undefined || audience.trafficPercent !== undefined

  return [
    `# Digital Experiment Brief: ${spec.name}`,
    '',
    '## Hypothesis',
    spec.hypothesis,
    '',
    ...(spec.goal.trim()
      ? ['## Goal', spec.goal.trim(), '']
      : []),
    '## Channel',
    'Digital (MVP) — store experiments deferred',
    '',
    '## Experiment Type (system-derived)',
    `- Design: **${experimentType}**`,
    `- Rationale: ${typeRationale}`,
    '',
    '## Opportunity Sizing',
    ...opportunityLines,
    '',
    '## Metrics And Tracking',
    `- Feature description: ${metrics.featureDescription ?? '—'}`,
    `- Experiment maturity: ${metrics.experimentMaturity ?? '—'}`,
    `- Primary: ${formatMetricList(metrics.primaryMetrics)}`,
    `- Secondary: ${formatMetricList(metrics.secondaryMetrics)}`,
    `- Guardrails: ${formatMetricList(metrics.guardrailMetrics)}`,
    ...formatMetricInputLines(metrics.metricInputs),
    '',
    '## Power Calculator',
    `- Baseline IOR rate: ${power.baselineIor ?? '—'}`,
    `- Minimum detectable effect: ${power.mdePercent ?? '—'}% relative`,
    `- Significance level (α): ${power.alpha ?? '—'}`,
    `- Statistical power (1−β): ${power.statisticalPower ?? '—'}`,
    `- Variants (incl. control): ${power.variants ?? '—'}`,
    `- Daily eligible traffic: ${power.dailyTraffic ?? '—'}`,
    `- Traffic fraction in experiment: ${power.trafficFraction ?? '—'}`,
    '',
    '## Audience (digital)',
    audienceConfigured
      ? [
          `- Segment: ${audience.segment ?? '—'}`,
          `- Traffic: ${audience.trafficPercent ?? '—'}%`,
          `- Exclusions: ${audience.exclusions || 'none'}`,
        ].join('\n')
      : '- Not configured yet — use Configure Audience on the brief handoff.',
  ].join('\n')
}

export interface ClassifyOptions {
  expectedLift?: number
  funnelStage?: FunnelStage
  addressableVolume?: number
  currentInteractionRate?: number
  targetInteractionRate?: number
}

export function buildMetricsFormDefaults(
  hypothesis: string,
  goal?: string,
  options?: number | ClassifyOptions,
): Record<string, unknown> {
  const opts: ClassifyOptions =
    typeof options === 'number' ? { expectedLift: options } : (options ?? {})
  // The classifier already derives the metric buckets from the hypothesis —
  // seeding them here means the form opens with a defensible starting set
  // instead of three empty boxes.
  const classified = classifyHypothesisMetrics(hypothesis, goal ?? '', opts)
  const names = (suggestions: { name: string }[]) => suggestions.map((m) => m.name).join(', ')

  return {
    featureDescription: hypothesis.trim().slice(0, 160),
    experimentMaturity: 'mvp',
    primaryMetrics: names(classified.primary),
    secondaryMetrics: names(classified.secondary),
    guardrailMetrics: names(classified.guardrail),
  }
}

export function buildExperimentTypeDefaults(
  hypothesis: string,
  goal: string,
  options?: number | ClassifyOptions,
): { experimentType: ExperimentTypeChoice; typeRationale: string; channelScope: string } {
  const opts: ClassifyOptions =
    typeof options === 'number' ? { expectedLift: options } : (options ?? {})
  const result = classifyHypothesisMetrics(hypothesis, goal, opts)
  return {
    experimentType: result.experimentType as ExperimentTypeChoice,
    typeRationale: result.typeRationale,
    channelScope: 'digital',
  }
}
