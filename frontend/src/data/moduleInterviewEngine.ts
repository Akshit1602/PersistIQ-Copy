import type { ModuleId, ProjectChannel } from '../context/types'
import { fillModuleDefaults } from './experimentBaselines'
import {
  prefillableValues,
  suggestFieldValues,
  type FieldSuggestion,
  type SuggestionContext,
} from './inputSuggestions'
import { getModuleFormSchema } from './moduleFormSchemas'
import { MODULE_BY_ID } from './moduleRegistry'
import type { InterviewFieldStep, InterviewPill } from '../context/conversationalLoopTypes'
import { getNextStepAfter, isWorkflowStepId } from './hypothesisWorkflow'

const POWER_CALCULATOR_STEPS: InterviewFieldStep[] = [
  {
    fieldKey: 'mdePercent',
    question:
      'What minimum detectable effect (% relative) should we design this test around?',
    pills: [
      { id: 'mde-5', label: '5% relative', value: 5, fieldKey: 'mdePercent' },
      { id: 'mde-10', label: '10% relative', value: 10, fieldKey: 'mdePercent' },
      { id: 'mde-15', label: '15% relative', value: 15, fieldKey: 'mdePercent' },
      { id: 'mde-20', label: '20% relative', value: 20, fieldKey: 'mdePercent' },
    ],
  },
  {
    fieldKey: 'alpha',
    question: 'Confirm the significance level (α):',
    pills: [
      { id: 'a-05', label: 'α=0.05', value: 0.05, fieldKey: 'alpha' },
      { id: 'a-01', label: 'α=0.01', value: 0.01, fieldKey: 'alpha' },
      { id: 'a-10', label: 'α=0.10', value: 0.1, fieldKey: 'alpha' },
    ],
  },
  {
    fieldKey: 'statisticalPower',
    question: 'What statistical power (1−β) should we target?',
    pills: [
      { id: 'p-80', label: '0.80', value: 0.8, fieldKey: 'statisticalPower' },
      { id: 'p-90', label: '0.90', value: 0.9, fieldKey: 'statisticalPower' },
      { id: 'p-70', label: '0.70', value: 0.7, fieldKey: 'statisticalPower' },
    ],
  },
]

const OPPORTUNITY_SIZING_STEPS: InterviewFieldStep[] = [
  {
    fieldKey: 'monthlyInquiries',
    question: 'What monthly inquiry volume should we size against?',
    pills: [
      { id: 'inq-10k', label: '10k / month', value: 10000, fieldKey: 'monthlyInquiries' },
      { id: 'inq-25k', label: '25k / month', value: 25000, fieldKey: 'monthlyInquiries' },
      { id: 'inq-50k', label: '50k / month', value: 50000, fieldKey: 'monthlyInquiries' },
      { id: 'inq-100k', label: '100k / month', value: 100000, fieldKey: 'monthlyInquiries' },
    ],
  },
  {
    fieldKey: 'currentIor',
    question: 'What is the current IOR (0–1)?',
    pills: [
      { id: 'ior-12', label: '0.12', value: 0.12, fieldKey: 'currentIor' },
      { id: 'ior-18', label: '0.18', value: 0.18, fieldKey: 'currentIor' },
      { id: 'ior-22', label: '0.22', value: 0.22, fieldKey: 'currentIor' },
    ],
  },
  {
    fieldKey: 'targetIor',
    question: 'What target IOR should the experiment aim for?',
    pills: [
      { id: 'tior-198', label: '0.198', value: 0.198, fieldKey: 'targetIor' },
      { id: 'tior-22', label: '0.22', value: 0.22, fieldKey: 'targetIor' },
      { id: 'tior-25', label: '0.25', value: 0.25, fieldKey: 'targetIor' },
    ],
  },
]

const METRICS_TRACKING_STEPS: InterviewFieldStep[] = [
  {
    fieldKey: 'featureDescription',
    question: 'Briefly describe the feature being tracked for this experiment:',
    pills: [
      {
        id: 'feat-checkout',
        label: 'Checkout UX',
        value: 'Checkout UX improvements',
        fieldKey: 'featureDescription',
      },
      {
        id: 'feat-pricing',
        label: 'Pricing display',
        value: 'Pricing display changes',
        fieldKey: 'featureDescription',
      },
      {
        id: 'feat-nav',
        label: 'Navigation',
        value: 'Navigation / findability changes',
        fieldKey: 'featureDescription',
      },
    ],
  },
  {
    fieldKey: 'experimentMaturity',
    question: 'What is the experiment maturity? (mvp=first test, iteration=refined, critical=high-stakes)',
    pills: [
      { id: 'mat-mvp', label: 'mvp', value: 'mvp', fieldKey: 'experimentMaturity' },
      { id: 'mat-iter', label: 'iteration', value: 'iteration', fieldKey: 'experimentMaturity' },
      { id: 'mat-crit', label: 'critical', value: 'critical', fieldKey: 'experimentMaturity' },
    ],
  },
]

const EXPERIMENT_TYPE_STEPS: InterviewFieldStep[] = [
  {
    fieldKey: 'experimentType',
    question: 'Confirm the recommended digital experiment type:',
    pills: [
      { id: 'type-ab', label: 'A/B', value: 'A/B', fieldKey: 'experimentType' },
      { id: 'type-abc', label: 'A/B/C', value: 'A/B/C', fieldKey: 'experimentType' },
      { id: 'type-causal', label: 'Causal', value: 'Causal', fieldKey: 'experimentType' },
    ],
  },
]

const AUDIENCE_SELECTION_STEPS: InterviewFieldStep[] = [
  {
    fieldKey: 'segment',
    question: 'Which digital audience segment should we target?',
    pills: [
      { id: 'seg-web', label: 'All web', value: 'all-web', fieldKey: 'segment' },
      { id: 'seg-app', label: 'Mobile app', value: 'mobile-app', fieldKey: 'segment' },
      { id: 'seg-new', label: 'New visitors', value: 'new-visitors', fieldKey: 'segment' },
    ],
  },
  {
    fieldKey: 'trafficPercent',
    question: 'What percent of eligible traffic should enter the test?',
    pills: [
      { id: 'tr-25', label: '25%', value: 25, fieldKey: 'trafficPercent' },
      { id: 'tr-50', label: '50%', value: 50, fieldKey: 'trafficPercent' },
      { id: 'tr-100', label: '100%', value: 100, fieldKey: 'trafficPercent' },
    ],
  },
]

const GENERIC_STEPS: InterviewFieldStep[] = [
  {
    fieldKey: 'notes',
    question: 'Describe any specific parameters or constraints for this module run:',
    pills: [
      { id: 'notes-default', label: 'Use experiment defaults', value: 'Defaults applied', fieldKey: 'notes' },
    ],
  },
]

const INTERVIEW_BY_MODULE: Partial<Record<ModuleId, InterviewFieldStep[]>> = {
  'power-calculator': POWER_CALCULATOR_STEPS,
  'opportunity-sizing': OPPORTUNITY_SIZING_STEPS,
  'metrics-tracking': METRICS_TRACKING_STEPS,
  'experiment-type': EXPERIMENT_TYPE_STEPS,
  'audience-selection': AUDIENCE_SELECTION_STEPS,
  'brief-generator': [],
}

export function getInterviewSteps(moduleId: ModuleId): InterviewFieldStep[] {
  return INTERVIEW_BY_MODULE[moduleId] ?? GENERIC_STEPS
}

export function bootstrapModuleParams(
  moduleId: ModuleId,
  experiment: string,
  existingParams?: Record<string, unknown>,
  suggestionContext?: SuggestionContext,
): { params: Record<string, unknown>; autoFilledFields: string[] } {
  const schema = getModuleFormSchema(moduleId, experiment)
  const defaults = Object.fromEntries(schema.fields.map((f) => [f.key, f.defaultValue]))
  // Schema defaults are the floor, so suggestions have to be applied against
  // the caller's values rather than merged underneath them.
  const suggestions = suggestionContext
    ? prefillableValues(suggestFieldValues(moduleId, suggestionContext), existingParams ?? {})
    : { values: {}, filledKeys: [] as string[] }
  const { values, autoFilled } = fillModuleDefaults(
    moduleId,
    experiment,
    {
      ...defaults,
      ...suggestions.values,
      ...(existingParams ?? {}),
    },
    suggestionContext,
  )
  const params = { ...values, ...(existingParams ?? {}) }

  // Suggested seeds (metrics/type/brief) count as auto-filled so interview skips those turns
  const suggestedKeys =
    existingParams &&
    (moduleId === 'metrics-tracking' ||
      moduleId === 'experiment-type' ||
      moduleId === 'brief-generator')
      ? Object.keys(existingParams).filter(
          (k) => existingParams[k] !== undefined && existingParams[k] !== '',
        )
      : []

  const autoFilledFields = [
    ...new Set([...autoFilled, ...suggestions.filledKeys, ...suggestedKeys]),
  ]
  return { params, autoFilledFields }
}

export function buildAutoFillSummary(
  moduleId: ModuleId,
  experiment: string,
  autoFilledFields: string[],
  params: Record<string, unknown>,
  channel: ProjectChannel = 'digital',
  suggestions: Record<string, FieldSuggestion> = {},
): string {
  if (autoFilledFields.length === 0) {
    return `Starting ${MODULE_BY_ID[moduleId].label} for "${experiment}" (${channel} MVP).`
  }
  // Name the source per field so the chat never implies data provenance the
  // value does not have.
  const details = autoFilledFields
    .map((key) => {
      const source = suggestions[key]?.label
      return `${key}=${JSON.stringify(params[key])}${source ? ` (${source})` : ''}`
    })
    .join(', ')
  return `I've pulled suggested inputs for "${experiment}" (${details}). I'll confirm the remaining inputs with you one at a time.`
}

export function getNextInterviewStep(
  moduleId: ModuleId,
  confirmedFieldKeys: string[],
): InterviewFieldStep | null {
  const steps = getInterviewSteps(moduleId)
  return steps.find((step) => !confirmedFieldKeys.includes(step.fieldKey)) ?? null
}

function proceedPillFor(moduleId: ModuleId): InterviewPill | null {
  if (!isWorkflowStepId(moduleId)) return null
  const next = getNextStepAfter(moduleId)
  if (!next) return null
  return {
    id: `proceed-${next.id}`,
    label: `Proceed to ${next.label}`,
    value: `__proceed__:${next.moduleId}`,
    fieldKey: '__proceed__',
  }
}

function formatPillValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

/**
 * Leads the offered options with the engine's suggestion for the field being
 * asked about, so the fastest answer is also the one grounded in the
 * experiment's own data rather than a fixed guess.
 */
function suggestedPillFor(
  fieldKey: string,
  suggestions: Record<string, FieldSuggestion>,
): InterviewPill | null {
  const suggestion = suggestions[fieldKey]
  if (!suggestion || suggestion.value === undefined || suggestion.value === '') return null
  return {
    id: `suggested-${fieldKey}`,
    label: `${formatPillValue(suggestion.value)} — ${suggestion.label}`,
    value: suggestion.value,
    fieldKey,
  }
}

export function getSmartPillsForPhase(
  moduleId: ModuleId,
  confirmedFieldKeys: string[],
  interviewPhase: 'interviewing' | 'ready' | 'idle' | 'running' | 'complete',
  suggestionContext?: SuggestionContext,
): InterviewPill[] {
  if (interviewPhase === 'complete') {
    const proceed = proceedPillFor(moduleId)
    return proceed ? [proceed] : []
  }
  if (interviewPhase === 'ready') {
    return [
      {
        id: 'run-simulation',
        label: '🚀 Run Simulation Now',
        value: '__run__',
        fieldKey: '__run__',
      },
    ]
  }
  if (interviewPhase !== 'interviewing') return []
  const next = getNextInterviewStep(moduleId, confirmedFieldKeys)
  if (!next) return []

  const suggestions = suggestionContext
    ? suggestFieldValues(moduleId, suggestionContext)
    : {}
  const suggested = suggestedPillFor(next.fieldKey, suggestions)
  if (!suggested) return next.pills

  // Drop any fixed option that duplicates the suggestion.
  const rest = next.pills.filter((p) => String(p.value) !== String(suggested.value))
  return [suggested, ...rest]
}

export function buildReadyMessage(moduleId: ModuleId): string {
  return `All parameters for ${MODULE_BY_ID[moduleId].label} are locked. Select **Run Simulation Now** when you're ready — results will stream inline in this chat.`
}

export function parseInterviewAnswerFromText(
  moduleId: ModuleId,
  fieldKey: string,
  text: string,
): unknown | null {
  const step = getInterviewSteps(moduleId).find((s) => s.fieldKey === fieldKey)
  if (!step) return text

  const pill = step.pills.find(
    (p) => p.label.toLowerCase() === text.trim().toLowerCase() || String(p.value) === text.trim(),
  )
  if (pill) return pill.value

  const asNumber = Number(text.replace(/[,%]/g, ''))
  if (!Number.isNaN(asNumber) && text.trim() !== '') return asNumber

  return text
}
