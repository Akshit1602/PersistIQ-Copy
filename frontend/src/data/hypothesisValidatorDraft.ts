import type { ExperimentTypeChoice } from '../context/types'
import { buildExperimentTypeDefaults } from './briefBuilder'
import { getMetricInputsForSelection, METRIC_KPI_BY_ID } from './metricCatalog'

export const VALIDATOR_STEPS = [
  { id: 1 as const, label: 'Hypothesis', short: 'Hypothesis' },
  { id: 2 as const, label: 'Opportunity', short: 'Sizing' },
  { id: 3 as const, label: 'Metrics', short: 'Metrics' },
  { id: 4 as const, label: 'Power', short: 'Power' },
  { id: 5 as const, label: 'Review', short: 'Review' },
]

export type ValidatorStepIndex = (typeof VALIDATOR_STEPS)[number]['id']

export type ExperimentMaturity = 'mvp' | 'iteration' | 'critical'

/**
 * Starting values for a blank draft. Deliberately plain defaults, not claims:
 * anything actually derived arrives from the suggestion engine and is rendered
 * with its provenance in the wizard.
 */
const OPPORTUNITY_STARTING_VALUES = {
  monthlyInquiries: 10000,
  currentIor: 0.18,
  aov: 500,
} as const

const POWER_STARTING_VALUES = {
  baselineIor: 0.18,
  dailyTraffic: 500,
} as const

export interface HypothesisValidatorDraft {
  name: string
  hypothesis: string
  goal: string
  opportunity: {
    skipped: boolean
    channelScope: string
    monthlyInquiries: number
    currentIor: number
    targetIor: number
    aov: number
    grossMargin: number
    timeHorizonMonths: number
  }
  metrics: {
    featureDescription: string
    experimentMaturity: ExperimentMaturity
    primaryMetricIds: string[]
    secondaryMetricIds: string[]
    guardrailMetricIds: string[]
    /** KPI id → input key → value (primary/secondary only) */
    metricInputs: Record<string, Record<string, string>>
    /** Store channel only: alert threshold/direction for the selected guardrail */
    guardrailThreshold?: number | null
    guardrailDirection?: 'below' | 'above'
  }
  derivedExperimentType: ExperimentTypeChoice
  typeRationale: string
  power: {
    baselineIor: number
    mdePercent: number
    alpha: number
    statisticalPower: number
    variants: number
    dailyTraffic: number
    trafficFraction: number
  }
}

export function createEmptyValidatorDraft(): HypothesisValidatorDraft {
  return {
    name: '',
    hypothesis: '',
    goal: '',
    opportunity: {
      skipped: false,
      channelScope: 'digital',
      monthlyInquiries: OPPORTUNITY_STARTING_VALUES.monthlyInquiries,
      currentIor: OPPORTUNITY_STARTING_VALUES.currentIor,
      targetIor: 0.198,
      aov: OPPORTUNITY_STARTING_VALUES.aov,
      grossMargin: 0.3,
      timeHorizonMonths: 12,
    },
    metrics: {
      featureDescription: '',
      experimentMaturity: 'mvp',
      primaryMetricIds: [],
      secondaryMetricIds: [],
      guardrailMetricIds: [],
      metricInputs: {},
      guardrailThreshold: null,
      guardrailDirection: 'below',
    },
    derivedExperimentType: 'A/B',
    typeRationale: '',
    power: {
      baselineIor: POWER_STARTING_VALUES.baselineIor,
      mdePercent: 10,
      alpha: 0.05,
      statisticalPower: 0.8,
      variants: 2,
      dailyTraffic: POWER_STARTING_VALUES.dailyTraffic,
      trafficFraction: 1,
    },
  }
}

function opportunityClassifyOptions(opp: HypothesisValidatorDraft['opportunity']) {
  if (opp.skipped) return {}
  return {
    addressableVolume: opp.monthlyInquiries || undefined,
    currentInteractionRate: opp.currentIor > 0 ? opp.currentIor * 100 : undefined,
    targetInteractionRate: opp.targetIor > 0 ? opp.targetIor * 100 : undefined,
  }
}

export function seedDerivedTypeFromDraft(
  draft: HypothesisValidatorDraft,
): HypothesisValidatorDraft {
  const opts = draft.opportunity.skipped ? {} : opportunityClassifyOptions(draft.opportunity)
  const defaults = buildExperimentTypeDefaults(draft.hypothesis, draft.goal, opts)
  return {
    ...draft,
    derivedExperimentType: defaults.experimentType as ExperimentTypeChoice,
    typeRationale: String(defaults.typeRationale),
  }
}

export function isStepValid(draft: HypothesisValidatorDraft, step: ValidatorStepIndex): boolean {
  switch (step) {
    case 1:
      return Boolean(draft.name.trim() && draft.hypothesis.trim())
    case 2:
      // Opportunity is optional; Next always allowed once on this step
      return true
    case 3: {
      const { primaryMetricIds, secondaryMetricIds, metricInputs } = draft.metrics
      if (primaryMetricIds.length === 0) return false
      const requiredInputs = [
        ...getMetricInputsForSelection(primaryMetricIds),
        ...getMetricInputsForSelection(secondaryMetricIds),
      ]
      return requiredInputs.every(({ kpiId, inputs }) =>
        inputs.every((field) => {
          if (field.required === false) return true
          const val = metricInputs[kpiId]?.[field.key]?.trim() ?? ''
          return val.length > 0
        }),
      )
    }
    case 4:
      return (
        draft.power.baselineIor > 0 &&
        draft.power.baselineIor <= 1 &&
        draft.power.mdePercent > 0 &&
        draft.power.alpha > 0 &&
        draft.power.alpha < 1 &&
        draft.power.statisticalPower > 0 &&
        draft.power.statisticalPower < 1 &&
        draft.power.variants >= 2 &&
        draft.power.dailyTraffic > 0 &&
        draft.power.trafficFraction > 0 &&
        draft.power.trafficFraction <= 1
      )
    case 5:
      return Boolean(draft.derivedExperimentType && draft.typeRationale)
    default:
      return false
  }
}

export function draftToModuleSnapshots(
  draft: HypothesisValidatorDraft,
): Partial<Record<string, Record<string, unknown>>> {
  const { skipped, ...opportunityFields } = draft.opportunity
  const iorLift =
    draft.opportunity.targetIor > 0 && draft.opportunity.currentIor > 0
      ? Math.round((draft.opportunity.targetIor - draft.opportunity.currentIor) * 1000) / 10
      : draft.power.mdePercent
  return {
    'opportunity-sizing': {
      ...opportunityFields,
      skipped,
      expectedLift: iorLift,
    },
    'metrics-tracking': {
      featureDescription:
        draft.metrics.featureDescription.trim() || draft.hypothesis.trim().slice(0, 160),
      experimentMaturity: draft.metrics.experimentMaturity || 'mvp',
      primaryMetrics: draft.metrics.primaryMetricIds.map((id) => METRIC_KPI_BY_ID[id]?.label ?? id),
      secondaryMetrics: draft.metrics.secondaryMetricIds.map(
        (id) => METRIC_KPI_BY_ID[id]?.label ?? id,
      ),
      guardrailMetrics: draft.metrics.guardrailMetricIds.map(
        (id) => METRIC_KPI_BY_ID[id]?.label ?? id,
      ),
      primaryMetricIds: draft.metrics.primaryMetricIds,
      secondaryMetricIds: draft.metrics.secondaryMetricIds,
      guardrailMetricIds: draft.metrics.guardrailMetricIds,
      metricInputs: draft.metrics.metricInputs,
      metricsApproved: true,
    },
    'experiment-type': {
      experimentType: draft.derivedExperimentType,
      typeRationale: draft.typeRationale,
      channelScope: 'digital',
    },
    'power-calculator': { ...draft.power },
  }
}

export function downloadMarkdownFile(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.md') ? filename : `${filename}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
