/**
 * The single suggestion engine behind every MatchView input.
 *
 * Resolution order per field, highest wins:
 *   1. dataset          — derived from the selected experiment's own data (backend)
 *   2. prior-run        — a value already locked in another module of this experiment
 *   3. hypothesis       — classified from this experiment's hypothesis/goal text
 *   4. derived          — arithmetic on values we already hold (e.g. target = current + MDE)
 *   5. project-history  — the same field on a sibling experiment in this project
 *   6. benchmark        — funnel-stage industry benchmark, never pre-filled
 *
 * Anything ranked `high` or `medium` pre-fills an untouched field; `low`
 * (benchmark) only ever offers a chip. A field with no suggestion renders no
 * provenance badge at all — silence beats a false "auto-detected" claim.
 */

import type { ExperimentSpec, ModuleId, ProjectChannel } from '../context/types'
import { suggestIndustryBenchmarks } from './industryBenchmarks'
import { classifyHypothesisMetrics, detectFunnelStage } from './metricClassifier'
import { METRIC_KPI_OPTIONS } from './metricCatalog'

export type SuggestionSource =
  | 'dataset'
  | 'prior-run'
  | 'hypothesis'
  | 'derived'
  | 'project-history'
  | 'benchmark'

export type SuggestionConfidence = 'high' | 'medium' | 'low'

export interface FieldSuggestion {
  value: unknown
  source: SuggestionSource
  confidence: SuggestionConfidence
  /** Shown in the field tooltip — the "why this number" answer. */
  rationale: string
  /** Period the underlying data covers, when the source knows one. */
  asOf?: string
  /** Short badge text, e.g. "from your quote data". */
  label: string
}

/** One field of the backend profile (see continum/mapMeta/baseline_profiler.py). */
export interface DatasetField {
  value: number
  source: string
  confidence: string
  rationale: string
  row_count: number
  as_of?: string | null
}

export type DatasetFieldMap = Record<string, DatasetField>

export interface SuggestionContext {
  experiment: string
  channel: ProjectChannel
  spec?: ExperimentSpec
  /** Module form values for THIS experiment. */
  moduleValues: Partial<Record<ModuleId, Record<string, unknown>>>
  /** Module form values for other experiments in the same project. */
  siblingValues: Record<string, Partial<Record<ModuleId, Record<string, unknown>>>>
  /** Backend-derived baselines for this experiment, keyed by form field. */
  datasetFields: DatasetFieldMap
}

/**
 * Scopes double as module ids where a module owns the fields. The digital
 * hypothesis wizard reuses 'opportunity-sizing' / 'power-calculator' because
 * its draft uses the same field keys; only the store wizard needs its own.
 */
export type SuggestionScope =
  | ModuleId
  | 'store-sizing'
  | 'store-rollout'
  | 'store-metrics'
  | 'wizard-metrics'

const SOURCE_LABELS: Record<SuggestionSource, string> = {
  dataset: 'from your data',
  'prior-run': 'from this experiment',
  hypothesis: 'from your hypothesis',
  derived: 'derived',
  'project-history': 'from this project',
  benchmark: 'industry benchmark',
}

const CONFIDENCE_BY_SOURCE: Record<SuggestionSource, SuggestionConfidence> = {
  dataset: 'high',
  'prior-run': 'high',
  hypothesis: 'medium',
  derived: 'medium',
  'project-history': 'medium',
  benchmark: 'low',
}

/** Which backend profile fields belong to which scope. */
const DATASET_FIELDS_BY_SCOPE: Partial<Record<SuggestionScope, string[]>> = {
  'power-calculator': ['baselineIor', 'dailyTraffic', 'variants'],
  'opportunity-sizing': ['monthlyInquiries', 'currentIor', 'aov', 'grossMargin'],
  'store-sizing': [
    'targetStoreCount',
    'weeklyStoreTraffic',
    'baselineCvr',
    'baselineAur',
    'grossMargin',
  ],
  'store-rollout': ['targetStoreCount'],
}

interface CrossFieldLink {
  module: ModuleId
  key: string
  transform?: (value: number) => number
  note: string
}

/**
 * Values already locked elsewhere in this experiment. Keeps the modules
 * arithmetically coherent instead of letting each form invent its own baseline.
 */
const CROSS_FIELD_LINKS: Record<string, CrossFieldLink[]> = {
  baselineIor: [
    { module: 'opportunity-sizing', key: 'currentIor', note: 'current IOR from Opportunity Sizing' },
  ],
  currentIor: [
    { module: 'power-calculator', key: 'baselineIor', note: 'baseline IOR from Power Calculator' },
  ],
  monthlyInquiries: [
    {
      module: 'power-calculator',
      key: 'dailyTraffic',
      transform: (v) => Math.round(v * 30),
      note: 'daily eligible traffic from Power Calculator, over 30 days',
    },
  ],
  dailyTraffic: [
    {
      module: 'opportunity-sizing',
      key: 'monthlyInquiries',
      transform: (v) => Math.round(v / 30),
      note: 'monthly inquiries from Opportunity Sizing, over 30 days',
    },
  ],
  mdePercent: [
    { module: 'opportunity-sizing', key: 'expectedLift', note: 'expected lift from Opportunity Sizing' },
  ],
  variants: [
    {
      module: 'experiment-type',
      key: 'experimentType',
      // 'A/B/C' -> 3, 'A/B' -> 2. Kept as a transform-free lookup below.
      note: 'experiment type',
    },
  ],
}

function _round(value: number, digits: number): number {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function isBlank(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    value === '' ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === 'number' && Number.isNaN(value))
  )
}

function make(
  value: unknown,
  source: SuggestionSource,
  rationale: string,
  asOf?: string,
): FieldSuggestion {
  return {
    value,
    source,
    confidence: CONFIDENCE_BY_SOURCE[source],
    rationale,
    asOf,
    label: SOURCE_LABELS[source],
  }
}

/** High/medium suggestions pre-fill an untouched field; benchmarks only offer a chip. */
export function shouldPrefill(suggestion: FieldSuggestion): boolean {
  return suggestion.confidence !== 'low'
}

// ---------------------------------------------------------------------------
// Individual sources
// ---------------------------------------------------------------------------

/**
 * Store KPI ids we can only propose because the profile actually measured a
 * baseline for them — profile field -> store catalog id.
 */
const STORE_METRIC_BY_PROFILE_FIELD: Record<string, { id: string; role: 'primary' | 'secondary' }> =
  {
    baselineCvr: { id: 'conversion_rate', role: 'primary' },
    baselineAur: { id: 'aur', role: 'secondary' },
    weeklyStoreTraffic: { id: 'traffic', role: 'secondary' },
    grossMargin: { id: 'gross_margin', role: 'secondary' },
  }

function fromDataset(scope: SuggestionScope, ctx: SuggestionContext): Record<string, FieldSuggestion> {
  const out: Record<string, FieldSuggestion> = {}

  if (scope === 'store-metrics') {
    const buckets: Record<'primary' | 'secondary', string[]> = { primary: [], secondary: [] }
    const evidence: string[] = []
    for (const [field, metric] of Object.entries(STORE_METRIC_BY_PROFILE_FIELD)) {
      const detail = ctx.datasetFields[field]
      if (!detail) continue
      buckets[metric.role].push(metric.id)
      evidence.push(detail.rationale)
    }
    if (buckets.primary.length > 0) {
      out.primaryMetrics = make(buckets.primary, 'dataset', evidence[0] ?? '')
    }
    if (buckets.secondary.length > 0) {
      out.secondaryMetrics = make(
        buckets.secondary,
        'dataset',
        'KPIs the store feed already reports a baseline for, so power analysis has real inputs',
      )
    }
    return out
  }

  if (scope === 'wizard-metrics') {
    // The KPI baseline boxes are required to leave the metrics step, and they
    // are exactly the numbers the profile already measured.
    const ior = ctx.datasetFields.baselineIor
    const aov = ctx.datasetFields.aov
    if (ior) {
      out['metricInputs.cvr.baseline'] = make(
        _round(ior.value * 100, 2),
        'dataset',
        `${ior.rationale} (${ior.source})`,
        ior.as_of ?? undefined,
      )
    }
    if (aov) {
      out['metricInputs.aov.baseline'] = make(
        _round(aov.value, 2),
        'dataset',
        `${aov.rationale} (${aov.source})`,
        aov.as_of ?? undefined,
      )
    }
    return out
  }

  const keys = DATASET_FIELDS_BY_SCOPE[scope] ?? []
  for (const key of keys) {
    const field = ctx.datasetFields[key]
    if (!field || typeof field.value !== 'number' || Number.isNaN(field.value)) continue
    out[key] = make(field.value, 'dataset', `${field.rationale} (${field.source})`, field.as_of ?? undefined)
  }
  return out
}

function fromPriorRuns(ctx: SuggestionContext): Record<string, FieldSuggestion> {
  const out: Record<string, FieldSuggestion> = {}

  for (const [fieldKey, links] of Object.entries(CROSS_FIELD_LINKS)) {
    for (const link of links) {
      const raw = ctx.moduleValues[link.module]?.[link.key]
      if (isBlank(raw)) continue

      if (fieldKey === 'variants') {
        const variants = String(raw) === 'A/B/C' ? 3 : String(raw) === 'A/B' ? 2 : null
        if (variants === null) continue
        out[fieldKey] = make(variants, 'prior-run', `Matches the ${raw} design chosen in Experiment Type`)
        break
      }

      const numeric = typeof raw === 'number' ? raw : Number(raw)
      if (Number.isNaN(numeric)) continue
      const value = link.transform ? link.transform(numeric) : numeric
      out[fieldKey] = make(value, 'prior-run', `Matches the ${link.note}`)
      break
    }
  }

  return out
}

function fromProjectHistory(
  fieldKeys: string[],
  ctx: SuggestionContext,
): Record<string, FieldSuggestion> {
  const out: Record<string, FieldSuggestion> = {}

  for (const key of fieldKeys) {
    for (const [experiment, modules] of Object.entries(ctx.siblingValues)) {
      if (experiment === ctx.experiment) continue
      const hit = Object.values(modules).find((values) => values && !isBlank(values[key]))
      if (!hit) continue
      out[key] = make(hit[key], 'project-history', `Carried over from "${experiment}" in this project`)
      break
    }
  }

  return out
}

/** Catalog ids for labels the classifier produced; unknown labels drop out. */
function metricIdsFor(labels: string[]): string[] {
  return labels
    .map((label) => METRIC_KPI_OPTIONS.find((kpi) => kpi.label === label)?.id)
    .filter((id): id is string => Boolean(id))
}

function metricLabelsFor(names: string[]): string[] {
  // Prefer the shared KPI catalog label so metrics read the same everywhere.
  return names.map((name) => {
    const match = METRIC_KPI_OPTIONS.find(
      (kpi) => kpi.label.toLowerCase() === name.toLowerCase() || kpi.id === name.toLowerCase(),
    )
    return match?.label ?? name
  })
}

function fromHypothesis(
  scope: SuggestionScope,
  ctx: SuggestionContext,
): Record<string, FieldSuggestion> {
  const spec = ctx.spec
  if (!spec?.hypothesis?.trim()) return {}

  const sizing = ctx.moduleValues['opportunity-sizing'] ?? {}
  const classified = classifyHypothesisMetrics(spec.hypothesis, spec.goal ?? '', {
    addressableVolume:
      typeof sizing.monthlyInquiries === 'number' ? sizing.monthlyInquiries : undefined,
    currentInteractionRate: typeof sizing.currentIor === 'number' ? sizing.currentIor * 100 : undefined,
    targetInteractionRate: typeof sizing.targetIor === 'number' ? sizing.targetIor * 100 : undefined,
  })

  const out: Record<string, FieldSuggestion> = {}

  // Store KPIs live in their own catalog and the digital funnel classifier has
  // nothing useful to say about them, so they are suggested from the store
  // baselines we actually measured — and nothing else.
  if (scope === 'store-metrics') return {}

  if (scope === 'metrics-tracking' || scope === 'wizard-metrics') {
    out.featureDescription = make(
      spec.hypothesis.trim().slice(0, 160),
      'hypothesis',
      'First 160 characters of the hypothesis you wrote for this experiment',
    )

    // The Analytics Lab renders these as textareas and the wizards as
    // multi-selects, so the value shape follows the surface.
    const asIds = scope !== 'metrics-tracking'
    const bucket = (metrics: { name: string; rationale: string }[]) => {
      const labels = metricLabelsFor(metrics.map((m) => m.name))
      return make(
        asIds ? metricIdsFor(labels) : labels.join(', '),
        'hypothesis',
        metrics.map((m) => `${m.name}: ${m.rationale}`).join(' '),
      )
    }

    out.primaryMetrics = bucket(classified.primary)
    out.secondaryMetrics = bucket(classified.secondary)
    out.guardrailMetrics = bucket(classified.guardrail)
  }

  if (scope === 'experiment-type') {
    out.experimentType = make(classified.experimentType, 'hypothesis', classified.typeRationale)
    out.typeRationale = make(classified.typeRationale, 'hypothesis', classified.funnelRationale)
  }

  if (scope === 'learnings-repository') {
    const keywords = [...new Set(`${spec.hypothesis} ${spec.goal ?? ''}`.toLowerCase().match(/[a-z]{4,}/g) ?? [])]
      .slice(0, 6)
      .join(', ')
    if (keywords) {
      out.keywords = make(keywords, 'hypothesis', 'Distinctive terms pulled from this experiment’s hypothesis and goal')
    }
  }

  return out
}

function fromDerived(
  scope: SuggestionScope,
  ctx: SuggestionContext,
  resolved: Record<string, FieldSuggestion>,
): Record<string, FieldSuggestion> {
  const out: Record<string, FieldSuggestion> = {}

  const numeric = (key: string, module: ModuleId): number | undefined => {
    const own = ctx.moduleValues[module]?.[key]
    if (typeof own === 'number') return own
    const suggested = resolved[key]?.value
    return typeof suggested === 'number' ? suggested : undefined
  }

  if (scope === 'opportunity-sizing') {
    const current = numeric('currentIor', 'opportunity-sizing')
    const mde =
      (typeof ctx.moduleValues['power-calculator']?.mdePercent === 'number'
        ? (ctx.moduleValues['power-calculator']?.mdePercent as number)
        : undefined) ?? 10
    if (current !== undefined && current > 0) {
      out.targetIor = make(
        Math.round(current * (1 + mde / 100) * 10000) / 10000,
        'derived',
        `Current IOR ${current} lifted by the ${mde}% minimum detectable effect`,
      )
    }
  }

  if (scope === 'store-sizing') {
    const cvr = numeric('baselineCvr', 'audience-selection') ?? (resolved.baselineCvr?.value as number | undefined)
    if (typeof cvr === 'number' && cvr > 0) {
      out.targetCvrLift = make(
        Math.round(cvr * 0.05 * 10000) / 10000,
        'derived',
        `A 5% relative lift on the measured ${cvr} baseline conversion rate`,
      )
    }
  }

  return out
}

function fromBenchmarks(
  scope: SuggestionScope,
  ctx: SuggestionContext,
): Record<string, FieldSuggestion> {
  if (scope !== 'opportunity-sizing') return {}

  const text = `${ctx.spec?.hypothesis ?? ''} ${ctx.spec?.goal ?? ''}`.trim() || ctx.experiment
  const { stage, rationale } = detectFunnelStage(text)
  const benchmarks = suggestIndustryBenchmarks(stage)
  const why = (what: string) => `${what} for ${stage} experiments. ${rationale}`

  return {
    monthlyInquiries: make(benchmarks.monthlyInquiries, 'benchmark', why('Typical monthly inquiry volume')),
    currentIor: make(
      Math.round((benchmarks.currentInteractionRate / 100) * 10000) / 10000,
      'benchmark',
      why('Typical interaction rate'),
    ),
    targetIor: make(
      Math.round((benchmarks.targetInteractionRate / 100) * 10000) / 10000,
      'benchmark',
      why('Typical post-experiment interaction rate'),
    ),
    aov: make(benchmarks.aov, 'benchmark', why('Typical average order value')),
    grossMargin: make(
      Math.round((benchmarks.grossMargin / 100) * 100) / 100,
      'benchmark',
      why('Typical gross margin'),
    ),
    timeHorizonMonths: make(
      Math.max(1, Math.round(benchmarks.timeHorizonWeeks / 4)),
      'benchmark',
      why('Typical measurement horizon'),
    ),
  }
}

// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------

export function createSuggestionContext(
  partial: Partial<SuggestionContext> & { experiment: string },
): SuggestionContext {
  return {
    channel: 'digital',
    moduleValues: {},
    siblingValues: {},
    datasetFields: {},
    ...partial,
  }
}

/**
 * Every suggestion available for a scope, best source per field. Callers decide
 * what to do with them: `shouldPrefill` separates pre-fill from click-to-apply.
 */
export function suggestFieldValues(
  scope: SuggestionScope,
  ctx: SuggestionContext,
): Record<string, FieldSuggestion> {
  const resolved: Record<string, FieldSuggestion> = {}

  const merge = (candidates: Record<string, FieldSuggestion>) => {
    for (const [key, suggestion] of Object.entries(candidates)) {
      if (isBlank(suggestion.value)) continue
      if (resolved[key]) continue // first writer wins — sources are applied best-first
      resolved[key] = suggestion
    }
  }

  merge(fromDataset(scope, ctx))
  merge(fromPriorRuns(ctx))
  merge(fromHypothesis(scope, ctx))
  merge(fromDerived(scope, ctx, resolved))

  const benchmarks = fromBenchmarks(scope, ctx)
  merge(fromProjectHistory([...Object.keys(benchmarks), ...(DATASET_FIELDS_BY_SCOPE[scope] ?? [])], ctx))
  merge(benchmarks)

  return resolved
}

/**
 * Values safe to write into an untouched form: high/medium confidence only, and
 * never over a field the user already filled in.
 */
export function prefillableValues(
  suggestions: Record<string, FieldSuggestion>,
  existing: Record<string, unknown> = {},
): { values: Record<string, unknown>; filledKeys: string[] } {
  const values: Record<string, unknown> = {}
  const filledKeys: string[] = []

  for (const [key, suggestion] of Object.entries(suggestions)) {
    if (!shouldPrefill(suggestion)) continue
    if (!isBlank(existing[key])) continue
    values[key] = suggestion.value
    filledKeys.push(key)
  }

  return { values, filledKeys }
}

/** One-line provenance sentence for chat replies. */
export function describeSuggestion(fieldKey: string, suggestion: FieldSuggestion): string {
  return `${fieldKey}=${JSON.stringify(suggestion.value)} (${suggestion.label})`
}
