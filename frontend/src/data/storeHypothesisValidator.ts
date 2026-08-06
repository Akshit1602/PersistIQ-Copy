/**
 * Store Channel — Initiative Setup & Benchmarking: Opportunity Sizing Step
 *
 * Replaces the digital channel's generic opportunity sizing with a
 * store-specific structure split into:
 *   Section 1: User Inputs (3 rows of input fields)
 *   Section 2: Dynamic Outputs (real-time calculation card)
 *
 * Used by HypothesisValidatorPanel.tsx when channel === 'store'
 */

import type { ExperimentTypeChoice } from '../context/types'

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: User Input Interfaces
// ═══════════════════════════════════════════════════════════════════════════════

/** Row 1: Scale & Time — The Foundation */
export interface StoreScaleInputs {
  targetStoreCount: number        // e.g., 500 stores
  weeklyStoreTraffic: number      // e.g., 10,000 customers/store
  timeHorizonMonths: number       // e.g., 12 months (short/long-term)
}

/** Row 2: Store Metrics — The Levers */
export interface StoreMetricInputs {
  baselineAur: number             // e.g., $1.25 (Average Unit Retail)
  baselineCvr: number             // e.g., 0.18 (18% conversion rate)
  targetCvrLift: number           // e.g., 0.012 (+1.2% absolute lift)
  baselineUpt: number             // e.g., 5.4 (Units Per Transaction)
  targetUptLift: number           // e.g., 0.3 (+0.3 units lift)
}

/** Row 3: Financials — The Costs */
export interface StoreFinancialInputs {
  grossMargin: number             // e.g., 0.31 (31%)
  estimatedInitiativeCost: number // e.g., 800000 ($800K)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Step 2 enhancements: visit-lag ramp, halo/cannibalization, net margin & iROAS
// ═══════════════════════════════════════════════════════════════════════════════

export interface StoreAdvancedDrivers {
  visitLagWeeks: number                  // 4-13 week Customer Visit Lag Window
  crossCategoryStoreHaloDollars: number   // $ spillover to other categories/channels
  inStoreCircularPopCost: number          // $ cost of in-store circular / point-of-purchase promo materials
  categoryCannibalizationPercent: number  // -5% from adjacent categories, still expressed as a % of gross profit
  mediaSpend: number | null               // optional, for iROAS
}

export const STORE_ADVANCED_DRIVERS_DEFAULTS: StoreAdvancedDrivers = {
  visitLagWeeks: 8,
  crossCategoryStoreHaloDollars: 15000,
  inStoreCircularPopCost: 12000,
  categoryCannibalizationPercent: 0.03,
  mediaSpend: null,
}

/** Smooth interpolation: a 4-week lag window only realizes ~30% of the
 * steady-state lift; a 13-week window realizes the full projected lift. */
export function computeVisitLagRampFactor(visitLagWeeks: number): number {
  const clamped = Math.max(4, Math.min(13, visitLagWeeks))
  return Math.round((0.3 + ((clamped - 4) / (13 - 4)) * 0.7) * 1000) / 1000
}

/** Complete user input state for Store Opportunity Sizing */
export interface StoreOpportunitySizing {
  scale: StoreScaleInputs
  metrics: StoreMetricInputs
  financials: StoreFinancialInputs
  advancedDrivers: StoreAdvancedDrivers
  skipped: boolean
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: Dynamic Output Calculations
// ═══════════════════════════════════════════════════════════════════════════════

/** The real-time calculation card outputs */
export interface StoreOpportunityOutputs {
  /** (Traffic × Target CVR × Target UPT × AUR) × Stores × Weeks */
  projectedIncrementalAnnualRevenue: number
  /** Revenue × Gross Margin */
  projectedIncrementalGrossProfit: number
  /** Gross Profit - Initiative Cost */
  projectedNetRoi: number
  /** Gross profit scaled down by the ramp horizon's realized fraction */
  rampAdjustedGrossProfit: number
  /** Ramp-adjusted profit + digital halo - category cannibalization - cost */
  netIncrementalMarginAfterHaloCannibalization: number
  /** (net incremental margin) / media spend, or null if no spend entered */
  incrementalRoas: number | null
}

/**
 * Compute the dynamic outputs from user inputs.
 * Called on every keystroke to update the Calculation Card in real-time.
 */
export function computeStoreOpportunityOutputs(
  inputs: StoreOpportunitySizing,
): StoreOpportunityOutputs {
  const { scale, metrics, financials } = inputs

  // Weeks in the time horizon
  const weeksInHorizon = scale.timeHorizonMonths * (52 / 12)

  // Current weekly revenue per store (baseline)
  const baselineWeeklyRevenuePerStore =
    scale.weeklyStoreTraffic * metrics.baselineCvr * metrics.baselineUpt * metrics.baselineAur

  // Target weekly revenue per store (with lifts applied)
  const targetCvr = metrics.baselineCvr + metrics.targetCvrLift
  const targetUpt = metrics.baselineUpt + metrics.targetUptLift
  const targetWeeklyRevenuePerStore =
    scale.weeklyStoreTraffic * targetCvr * targetUpt * metrics.baselineAur

  // Incremental revenue = (target - baseline) × stores × weeks
  const incrementalWeeklyPerStore = targetWeeklyRevenuePerStore - baselineWeeklyRevenuePerStore
  const projectedIncrementalAnnualRevenue =
    incrementalWeeklyPerStore * scale.targetStoreCount * weeksInHorizon

  // Gross profit = revenue × margin
  const projectedIncrementalGrossProfit =
    projectedIncrementalAnnualRevenue * financials.grossMargin

  // Net ROI = gross profit - initiative cost (original, unramped, full-year math)
  const projectedNetRoi =
    projectedIncrementalGrossProfit - financials.estimatedInitiativeCost

  // ── Step 2 enhancements ──
  const { advancedDrivers } = inputs
  const rampFactor = computeVisitLagRampFactor(advancedDrivers.visitLagWeeks)
  const rampAdjustedGrossProfit = projectedIncrementalGrossProfit * rampFactor

  const cannibalizationLoss = rampAdjustedGrossProfit * advancedDrivers.categoryCannibalizationPercent
  const netIncrementalMarginAfterHaloCannibalization =
    rampAdjustedGrossProfit +
    advancedDrivers.crossCategoryStoreHaloDollars -
    cannibalizationLoss -
    advancedDrivers.inStoreCircularPopCost -
    financials.estimatedInitiativeCost

  const incrementalRoas =
    advancedDrivers.mediaSpend && advancedDrivers.mediaSpend > 0
      ? netIncrementalMarginAfterHaloCannibalization / advancedDrivers.mediaSpend
      : null

  return {
    projectedIncrementalAnnualRevenue: Math.round(projectedIncrementalAnnualRevenue * 100) / 100,
    projectedIncrementalGrossProfit: Math.round(projectedIncrementalGrossProfit * 100) / 100,
    projectedNetRoi: Math.round(projectedNetRoi * 100) / 100,
    rampAdjustedGrossProfit: Math.round(rampAdjustedGrossProfit * 100) / 100,
    netIncrementalMarginAfterHaloCannibalization: Math.round(netIncrementalMarginAfterHaloCannibalization * 100) / 100,
    incrementalRoas: incrementalRoas !== null ? Math.round(incrementalRoas * 100) / 100 : null,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Defaults & Validation
// ═══════════════════════════════════════════════════════════════════════════════

/** Auto-detected baseline defaults (from UC table aggregates) */
export const STORE_OPPORTUNITY_DEFAULTS: StoreOpportunitySizing = {
  scale: {
    targetStoreCount: 500,
    weeklyStoreTraffic: 10000,
    timeHorizonMonths: 12,
  },
  metrics: {
    baselineAur: 1.25,
    baselineCvr: 0.18,
    targetCvrLift: 0.012,
    baselineUpt: 5.4,
    targetUptLift: 0.3,
  },
  financials: {
    grossMargin: 0.31,
    estimatedInitiativeCost: 800000,
  },
  advancedDrivers: STORE_ADVANCED_DRIVERS_DEFAULTS,
  skipped: false,
}

/** Validate that all required fields are filled for the sizing step */
export function isStoreOpportunitySizingValid(inputs: StoreOpportunitySizing): boolean {
  if (inputs.skipped) return true

  const { scale, metrics, financials } = inputs

  return (
    scale.targetStoreCount > 0 &&
    scale.weeklyStoreTraffic > 0 &&
    scale.timeHorizonMonths > 0 &&
    scale.timeHorizonMonths <= 36 &&
    metrics.baselineAur > 0 &&
    metrics.baselineCvr > 0 &&
    metrics.baselineCvr <= 1 &&
    metrics.targetCvrLift >= 0 &&
    (metrics.baselineCvr + metrics.targetCvrLift) <= 1 &&
    metrics.baselineUpt > 0 &&
    metrics.targetUptLift >= 0 &&
    financials.grossMargin > 0 &&
    financials.grossMargin <= 1 &&
    financials.estimatedInitiativeCost >= 0
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// Full Store Initiative Setup & Benchmarking Draft
// ═══════════════════════════════════════════════════════════════════════════════

export const STORE_VALIDATOR_STEPS = [
  { id: 1 as const, label: 'Initiative Setup', short: 'Initiative Setup' },
  { id: 2 as const, label: 'Opportunity Sizing', short: 'Sizing' },
  { id: 3 as const, label: 'Rollout & Store Targeting', short: 'Rollout & Store Targeting' },
  { id: 4 as const, label: 'Metrics', short: 'Metrics' },
  { id: 5 as const, label: 'Power Calculator', short: 'Power Calculator' },
  { id: 6 as const, label: 'Review & Concurrency', short: 'Review & Concurrency' },
]

export type StoreValidatorStepIndex = (typeof STORE_VALIDATOR_STEPS)[number]['id']

export interface StoreHypothesisValidatorDraft {
  name: string
  hypothesis: string
  goal: string
  initiative: {
    initiativeId: string
    initiativeCategory: string
    expectedLagWeeks: number
  }
  opportunity: StoreOpportunitySizing
  metrics: {
    primaryMetricIds: string[]
    secondaryMetricIds: string[]
    guardrailMetricIds: string[]
    metricInputs: Record<string, Record<string, string>>
  }
  derivedExperimentType: ExperimentTypeChoice
  typeRationale: string
  power: {
    baselineCvr: number
    mdePercent: number
    alpha: number
    statisticalPower: number
    variants: number
    weeklyTrafficPerStore: number
    storeCount: number
  }
}

export function createEmptyStoreValidatorDraft(): StoreHypothesisValidatorDraft {
  return {
    name: '',
    hypothesis: '',
    goal: '',
    initiative: {
      initiativeId: '',
      initiativeCategory: '',
      expectedLagWeeks: 4,
    },
    opportunity: { ...STORE_OPPORTUNITY_DEFAULTS },
    metrics: {
      primaryMetricIds: [],
      secondaryMetricIds: [],
      guardrailMetricIds: [],
      metricInputs: {},
    },
    derivedExperimentType: 'A/B',
    typeRationale: '',
    power: {
      baselineCvr: 0.18,
      mdePercent: 10,
      alpha: 0.05,
      statisticalPower: 0.8,
      variants: 2,
      weeklyTrafficPerStore: 10000,
      storeCount: 500,
    },
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// UI Field Definitions (for rendering the form)
// ═══════════════════════════════════════════════════════════════════════════════

export interface SizingFieldDef {
  key: string
  label: string
  placeholder: string
  type: 'number'
  min?: number
  max?: number
  step?: number
  suffix?: string
  prefix?: string
  info?: string
}

/** Row 1: Scale & Time fields */
export const SCALE_FIELDS: SizingFieldDef[] = [
  {
    key: 'targetStoreCount',
    label: 'Target Store Count',
    placeholder: 'e.g. 500',
    type: 'number',
    min: 1,
    max: 100000,
    step: 50,
    suffix: 'stores',
    info: 'Number of stores receiving the initiative (treatment group)',
  },
  {
    key: 'weeklyStoreTraffic',
    label: 'Weekly Store Traffic',
    placeholder: 'e.g. 10000',
    type: 'number',
    min: 100,
    step: 500,
    suffix: 'customers/store',
    info: 'Average weekly foot traffic per store from door sensor data',
  },
  {
    key: 'timeHorizonMonths',
    label: 'Time Horizon',
    placeholder: 'e.g. 12',
    type: 'number',
    min: 1,
    max: 36,
    step: 1,
    suffix: 'months',
    info: 'Measurement window accounting for initiative lag in customer behavior',
  },
]

/** Row 2: Store Metrics fields */
export const METRIC_FIELDS: SizingFieldDef[] = [
  {
    key: 'baselineAur',
    label: 'Unit Retail (AUR)',
    placeholder: 'e.g. 1.25',
    type: 'number',
    min: 0.01,
    step: 0.01,
    prefix: '$',
    info: 'Average selling price per unit — baseline from store_performance_weekly',
  },
  {
    key: 'baselineCvr',
    label: 'Baseline CVR Rate',
    placeholder: 'e.g. 18',
    type: 'number',
    min: 0,
    max: 100,
    step: 0.1,
    suffix: '%',
    info: 'Current traffic-to-transaction conversion rate from POS data',
  },
  {
    key: 'targetCvrLift',
    label: 'Target CVR Lift',
    placeholder: 'e.g. 1.2',
    type: 'number',
    min: 0,
    max: 50,
    step: 0.1,
    suffix: '% pts',
    info: 'Expected absolute percentage point improvement in conversion',
  },
  {
    key: 'baselineUpt',
    label: 'Baseline UPT',
    placeholder: 'e.g. 5.4',
    type: 'number',
    min: 0,
    step: 0.1,
    suffix: 'units',
    info: 'Current average units per transaction from POS basket data',
  },
  {
    key: 'targetUptLift',
    label: 'Target UPT Lift',
    placeholder: 'e.g. 0.3',
    type: 'number',
    min: 0,
    step: 0.1,
    suffix: 'units',
    info: 'Expected absolute improvement in basket depth',
  },
]

/** Row 3: Financial fields */
export const FINANCIAL_FIELDS: SizingFieldDef[] = [
  {
    key: 'grossMargin',
    label: 'Gross Margin',
    placeholder: 'e.g. 31',
    type: 'number',
    min: 0,
    max: 100,
    step: 0.5,
    suffix: '%',
    info: 'Category-level gross margin after COGS',
  },
  {
    key: 'estimatedInitiativeCost',
    label: 'Estimated Initiative Cost',
    placeholder: 'e.g. 800000',
    type: 'number',
    min: 0,
    step: 10000,
    prefix: '$',
    info: 'Total program cost (hiring, equipment, rollout) across all target stores',
  },
]

// ═══════════════════════════════════════════════════════════════════════════════
// Output Formatting Utilities
// ═══════════════════════════════════════════════════════════════════════════════

/** Format a dollar amount with commas and $ prefix */
export function formatCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`
  }
  return `${value.toFixed(2)}`
}

/** Format ROI as a percentage of cost */
export function formatRoiPercent(netRoi: number, cost: number): string {
  if (cost === 0) return 'N/A'
  const pct = (netRoi / cost) * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
}

/** Determine ROI health status for coloring the calculation card */
export function getRoiStatus(netRoi: number): 'positive' | 'neutral' | 'negative' {
  if (netRoi > 0) return 'positive'
  if (netRoi === 0) return 'neutral'
  return 'negative'
}
