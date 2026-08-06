import type { ModuleId } from '../context/types'
import { MODULE_BY_ID } from './moduleRegistry'

export type FieldType = 'number' | 'slider' | 'select' | 'textarea' | 'text' | 'toggle' | 'readonly'

export interface FormFieldSchema {
  key: string
  label: string
  type: FieldType
  defaultValue: unknown
  min?: number
  max?: number
  step?: number
  options?: { value: string; label: string }[]
  toggleLabel?: string
  placeholder?: string
  helpText?: string
  rows?: number
}

export interface ModuleFormSchema {
  moduleId: ModuleId
  fields: FormFieldSchema[]
}

const POWER_CALCULATOR_SCHEMA: ModuleFormSchema = {
  moduleId: 'power-calculator',
  fields: [
    {
      key: 'baselineIor',
      label: 'Baseline IOR rate (0–1)',
      type: 'number',
      defaultValue: 0.18,
      min: 0,
      max: 1,
      step: 0.0001,
      helpText: 'Auto-detected from historical data: 0.1800',
    },
    {
      key: 'mdePercent',
      label: 'Minimum detectable effect (% relative)',
      type: 'number',
      defaultValue: 10,
      min: 0.1,
      max: 100,
      step: 0.1,
      helpText: 'e.g. 10 means detect a 10% relative lift',
    },
    {
      key: 'alpha',
      label: 'Significance level α',
      type: 'number',
      defaultValue: 0.05,
      min: 0.001,
      max: 0.2,
      step: 0.01,
    },
    {
      key: 'statisticalPower',
      label: 'Statistical power 1−β',
      type: 'number',
      defaultValue: 0.8,
      min: 0.5,
      max: 0.99,
      step: 0.01,
    },
    {
      key: 'variants',
      label: 'Number of variants (incl. control)',
      type: 'number',
      defaultValue: 2,
      min: 2,
      max: 10,
      step: 1,
    },
    {
      key: 'dailyTraffic',
      label: 'Daily eligible traffic',
      type: 'number',
      defaultValue: 500,
      min: 1,
      step: 1,
      helpText: 'Auto-detected: 500 daily inquiries',
    },
    {
      key: 'trafficFraction',
      label: 'Traffic fraction in experiment (0–1)',
      type: 'number',
      defaultValue: 1,
      min: 0.01,
      max: 1,
      step: 0.01,
    },
  ],
}

const OPPORTUNITY_SIZING_SCHEMA: ModuleFormSchema = {
  moduleId: 'opportunity-sizing',
  fields: [
    {
      key: 'monthlyInquiries',
      label: 'Monthly inquiries',
      type: 'number',
      defaultValue: 10000,
      min: 0,
      max: 50000000,
      step: 100,
      placeholder: 'e.g. 10000',
    },
    {
      key: 'currentIor',
      label: 'Current IOR (0–1)',
      type: 'number',
      defaultValue: 0.18,
      min: 0,
      max: 1,
      step: 0.0001,
      placeholder: 'e.g. 0.18',
    },
    {
      key: 'targetIor',
      label: 'Target IOR after experiment',
      type: 'number',
      defaultValue: 0.198,
      min: 0,
      max: 1,
      step: 0.0001,
      placeholder: 'e.g. 0.198',
    },
    {
      key: 'aov',
      label: 'Average order value ($)',
      type: 'number',
      defaultValue: 500,
      min: 0,
      max: 100000,
      step: 1,
      placeholder: 'e.g. 500',
    },
    {
      key: 'grossMargin',
      label: 'Gross margin (0–1)',
      type: 'number',
      defaultValue: 0.3,
      min: 0,
      max: 1,
      step: 0.01,
      placeholder: 'e.g. 0.3',
    },
    {
      key: 'timeHorizonMonths',
      label: 'Time horizon (months)',
      type: 'number',
      defaultValue: 12,
      min: 1,
      max: 60,
      step: 1,
      placeholder: 'e.g. 12',
    },
  ],
}

const METRICS_TRACKING_SCHEMA: ModuleFormSchema = {
  moduleId: 'metrics-tracking',
  fields: [
    {
      key: 'featureDescription',
      label: 'Feature description',
      type: 'text',
      defaultValue: '',
      placeholder: 'Brief description of the feature being tracked',
      helpText: 'Brief description of the feature being tracked',
    },
    {
      key: 'experimentMaturity',
      label: 'Experiment maturity',
      type: 'select',
      defaultValue: 'mvp',
      helpText: 'mvp=first test, iteration=refined, critical=high-stakes',
      options: [
        { value: 'mvp', label: 'mvp' },
        { value: 'iteration', label: 'iteration' },
        { value: 'critical', label: 'critical' },
      ],
    },
    {
      key: 'primaryMetrics',
      label: 'Primary metrics',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'Selected primary KPIs…',
      rows: 2,
    },
    {
      key: 'secondaryMetrics',
      label: 'Secondary metrics',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'Selected secondary KPIs…',
      rows: 2,
    },
    {
      key: 'guardrailMetrics',
      label: 'Guardrail metrics',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'Selected guardrail KPIs…',
      rows: 2,
    },
  ],
}

const EXPERIMENT_TYPE_SCHEMA: ModuleFormSchema = {
  moduleId: 'experiment-type',
  fields: [
    {
      key: 'experimentType',
      label: 'Experiment Type',
      type: 'select',
      defaultValue: 'A/B',
      options: [
        { value: 'A/B', label: 'A/B' },
        { value: 'A/B/C', label: 'A/B/C' },
        { value: 'Causal', label: 'Causal' },
      ],
    },
    {
      key: 'typeRationale',
      label: 'Recommendation Rationale',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'Why this design fits the hypothesis…',
      rows: 3,
    },
    {
      key: 'channelScope',
      label: 'Channel Scope',
      type: 'select',
      defaultValue: 'digital',
      options: [{ value: 'digital', label: 'Digital (MVP)' }],
    },
  ],
}

const AUDIENCE_SELECTION_SCHEMA: ModuleFormSchema = {
  moduleId: 'audience-selection',
  fields: [
    {
      key: 'segment',
      label: 'Digital Segment',
      type: 'select',
      defaultValue: 'all-web',
      options: [
        { value: 'all-web', label: 'All web traffic' },
        { value: 'mobile-app', label: 'Mobile app' },
        { value: 'new-visitors', label: 'New visitors' },
        { value: 'returning-visitors', label: 'Returning visitors' },
        { value: 'logged-in', label: 'Logged-in users' },
      ],
    },
    {
      key: 'trafficPercent',
      label: 'Traffic Allocation (%)',
      type: 'slider',
      defaultValue: 50,
      min: 5,
      max: 100,
      step: 5,
    },
    {
      key: 'exclusions',
      label: 'Exclusions',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'e.g. employees, QA traffic, bot filters…',
      rows: 3,
    },
  ],
}

const BRIEF_GENERATOR_SCHEMA: ModuleFormSchema = {
  moduleId: 'brief-generator',
  fields: [
    {
      key: 'briefTitle',
      label: 'Brief Title',
      type: 'text',
      defaultValue: '',
      placeholder: 'Auto-filled from experiment name…',
    },
    {
      key: 'briefBody',
      label: 'Experiment Brief',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'Structured brief (hypothesis, goal, metrics, type, power, audience)…',
      rows: 10,
    },
  ],
}

const LEARNINGS_REPOSITORY_SCHEMA: ModuleFormSchema = {
  moduleId: 'learnings-repository',
  fields: [
    {
      key: 'keywords',
      label: 'Keywords',
      type: 'text',
      defaultValue: '',
      placeholder: 'e.g. banner, mobile, CVR lift',
    },
    {
      key: 'shipDecision',
      label: 'Ship Decision',
      type: 'select',
      defaultValue: 'Iterate',
      options: [
        { value: 'Ship', label: 'Ship' },
        { value: 'Iterate', label: 'Iterate' },
        { value: 'Kill', label: 'Kill' },
        { value: 'Hold', label: 'Hold' },
      ],
    },
    {
      key: 'keyLearning',
      label: 'Key Learning',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'Document the primary insight in markdown…',
      rows: 5,
    },
    {
      key: 'outcomeSummary',
      label: 'Outcome Summary',
      type: 'textarea',
      defaultValue: '',
      placeholder: 'Summarize measurable outcomes and next steps…',
      rows: 4,
    },
  ],
}

const MODULE_SCHEMAS: Partial<Record<ModuleId, ModuleFormSchema>> = {
  'power-calculator': POWER_CALCULATOR_SCHEMA,
  'opportunity-sizing': OPPORTUNITY_SIZING_SCHEMA,
  'metrics-tracking': METRICS_TRACKING_SCHEMA,
  'experiment-type': EXPERIMENT_TYPE_SCHEMA,
  'audience-selection': AUDIENCE_SELECTION_SCHEMA,
  'brief-generator': BRIEF_GENERATOR_SCHEMA,
  'learnings-repository': LEARNINGS_REPOSITORY_SCHEMA,
}

function buildGenericSchema(moduleId: ModuleId, experiment: string): ModuleFormSchema {
  const mod = MODULE_BY_ID[moduleId]
  return {
    moduleId,
    fields: [
      {
        key: 'notes',
        label: 'Configuration Notes',
        type: 'textarea',
        defaultValue: '',
        placeholder: `Optional parameters for ${mod.label} on ${experiment}…`,
        rows: 4,
      },
    ],
  }
}

export function getModuleFormSchema(moduleId: ModuleId, experiment: string): ModuleFormSchema {
  return MODULE_SCHEMAS[moduleId] ?? buildGenericSchema(moduleId, experiment)
}

export function getDefaultFormValues(schema: ModuleFormSchema): Record<string, unknown> {
  return Object.fromEntries(schema.fields.map((f) => [f.key, f.defaultValue]))
}
