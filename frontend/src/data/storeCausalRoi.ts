/**
 * Store Channel — Causal Inference & ROI (5 sub-modules)
 *   1. Causal Inference Engine (relabels 'causal-did')
 *   2. Forecasting & Counterfactual Predictor (relabels 'forecasting')
 *   3. ROI Synthesis — P&L Money Waterfall (relabels 'roi-synthesis')
 *   4. Simpson's Paradox & Heterogeneity Checker (relabels 'simpsons-paradox')
 *   5. Learnings & Meta-Analysis Repository (relabels 'learnings-repository')
 */

// ─────────────────────────────────────────────────────────────────────────────
// 1. Causal Inference Engine
// ─────────────────────────────────────────────────────────────────────────────

export type EstimatorEngine = 'sdid' | 'staggered_did' | 'dml' | 'its'

export const ESTIMATOR_ENGINE_OPTIONS: { value: EstimatorEngine; label: string; hint: string }[] = [
  { value: 'sdid', label: 'Synthetic Difference-in-Differences (SDID / BSTS)', hint: 'Default for matched-pair pilots' },
  { value: 'staggered_did', label: "Staggered DiD (Callaway & Sant'Anna)", hint: 'For multi-wave phased store rollouts' },
  { value: 'dml', label: 'Double / Debiased Machine Learning (DML)', hint: 'For isolating overlapping concurrent store initiatives' },
  { value: 'its', label: 'Interrupted Time Series (ITS)', hint: 'For 100% full-fleet rollouts with zero control stores' },
]

export interface ConfounderToggles {
  weatherNormalization: boolean
  stockoutVelocityMasking: boolean
  baselineVolumeDecileBalancing: boolean
}

export const CONFOUNDER_TOGGLES_DEFAULTS: ConfounderToggles = {
  weatherNormalization: true,
  stockoutVelocityMasking: true,
  baselineVolumeDecileBalancing: true,
}

export interface CausalInferenceResult {
  estimator: EstimatorEngine
  netLiftPercent: number
  netLiftDollars: number
  stdError: number
  pValue: number
  ciLo: number
  ciHi: number
  isSignificant: boolean
  ranAtIso: string
}

export function simulateCausalInference(
  estimator: EstimatorEngine,
  confounders: ConfounderToggles,
  testStoreCount: number,
): Promise<CausalInferenceResult> {
  return new Promise((resolve) => {
    const delayMs = 1800 + (testStoreCount % 800)
    window.setTimeout(() => {
      const seed = testStoreCount * 5 + estimator.length * 11
      const nAdjustments = Object.values(confounders).filter(Boolean).length
      // More confounder adjustments -> tighter (lower variance) estimate.
      const varianceReduction = 1 - nAdjustments * 0.08
      const baseLift = 1.5 + Math.abs(Math.sin(seed * 0.31)) * 2.5 // 1.5-4%
      const netLiftPercent = Math.round(baseLift * 100) / 100
      const stdError = Math.round(0.9 * varianceReduction * 100) / 100
      const zScore = netLiftPercent / stdError
      const pValue = Math.round(Math.max(0.0001, 2 * (1 - Math.min(0.9999, 0.5 + zScore / 8))) * 10000) / 10000
      const ciLo = Math.round((netLiftPercent - 1.96 * stdError) * 100) / 100
      const ciHi = Math.round((netLiftPercent + 1.96 * stdError) * 100) / 100
      const baseWeeklySales = 100_000 * testStoreCount
      const netLiftDollars = Math.round(baseWeeklySales * 52 * (netLiftPercent / 100))

      resolve({
        estimator,
        netLiftPercent,
        netLiftDollars,
        stdError,
        pValue,
        ciLo,
        ciHi,
        isSignificant: pValue < 0.05,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. Forecasting & Counterfactual Predictor
// ─────────────────────────────────────────────────────────────────────────────

export interface WeeklyForecastPoint {
  week: number
  predictedBaseline: number
  realizedSales: number
  incrementalDeltaDollars: number
  liftPercent: number
  ciLoPercent: number
  ciHiPercent: number
}

export interface FullFleetSimulationPoint {
  storeCount: number
  projectedAnnualLiftDollars: number
}

export type ForecastingModel = 'arima' | 'ets' | 'prophet' | 'lightgbm' | 'xgboost' | 'random_forest' | 'var' | 'dynamic_regression'

export const FORECASTING_MODEL_OPTIONS: { value: ForecastingModel; label: string; hint: string; description: string }[] = [
  { value: 'arima', label: 'ARIMA / SARIMA', hint: 'Classical statistical baseline for univariate time-series with trend and seasonality', description: 'Auto-Regressive Integrated Moving Average with optional Seasonal component (SARIMA). Decomposes a univariate series into autoregressive lags, differencing for stationarity, and moving-average error correction. Best suited for stable, well-structured seasonality and short-to-medium horizons where interpretability is valued.' },
  { value: 'ets', label: 'ETS (Exponential Smoothing)', hint: 'State-space model capturing error, trend, and seasonal components', description: 'Exponential Smoothing State Space model that explicitly decomposes a time series into Error, Trend, and Seasonal components (additive or multiplicative). Provides optimal point forecasts and prediction intervals via maximum likelihood, excelling on data with clear level shifts and dampened trends.' },
  { value: 'prophet', label: 'Prophet', hint: 'Robust to missing data, holiday effects, and trend changepoints', description: 'Facebook/Meta\'s additive regression model that fits piecewise-linear or logistic growth trends, Fourier-based seasonality, and user-specified holiday/event regressors. Handles missing data gracefully and automatically detects changepoints, making it ideal for business time-series with irregular patterns.' },
  { value: 'lightgbm', label: 'LightGBM', hint: 'Gradient-boosted trees optimized for speed and high-dimensional feature sets', description: 'A high-performance gradient boosting framework using histogram-based splitting and leaf-wise tree growth. Handles categorical features natively, scales to millions of rows with minimal tuning, and captures complex non-linear interactions between lag features, external regressors, and time-derived variables.' },
  { value: 'xgboost', label: 'XGBoost', hint: 'Regularized gradient boosting with strong out-of-the-box accuracy', description: 'Extreme Gradient Boosting builds an ensemble of decision trees with L1/L2 regularization to prevent overfitting. Supports custom loss functions, monotone constraints, and feature importance scoring — widely used as a tabular-data workhorse for forecasting when engineered lag/rolling features are provided.' },
  { value: 'random_forest', label: 'Random Forest Regressor', hint: 'Ensemble of bagged trees for stable, low-variance predictions', description: 'Aggregates predictions from hundreds of independently bootstrapped decision trees, reducing variance without increasing bias. Robust to outliers and noisy features, provides built-in feature importance, and serves as a strong non-parametric baseline that requires minimal hyperparameter tuning.' },
  { value: 'var', label: 'Vector Autoregression (VAR)', hint: 'Multivariate model capturing cross-variable feedback loops', description: 'A system of linear equations where each variable (sales, traffic, inventory) is regressed on its own lags and the lags of every other variable in the system. Captures Granger-causal feedback loops and produces impulse-response functions showing how a shock to one metric propagates across the system over time.' },
  { value: 'dynamic_regression', label: 'Dynamic Regression', hint: 'ARIMA errors with external regressors for intervention and covariate modeling', description: 'Combines ARIMA-style error modeling with external explanatory variables (promotions, holidays, macro indicators). The regression component captures the structural relationship with covariates while the ARIMA errors handle residual autocorrelation — ideal for forecasting with known future interventions or planned events.' },
]

export interface ForecastingResult {
  weeklyPoints: WeeklyForecastPoint[]
  horizonWeeks: 12 | 26 | 52
  model: ForecastingModel
  projectedFutureLiftPercent: number
  fullFleetSimulation: FullFleetSimulationPoint[]
  ranAtIso: string
}

export function simulateForecasting(
  testStoreCount: number,
  weeksOfFlight: number,
  horizonWeeks: 12 | 26 | 52,
  model: ForecastingModel = 'arima',
): Promise<ForecastingResult> {
  return new Promise((resolve) => {
    const delayMs = 1600 + (testStoreCount % 700)
    window.setTimeout(() => {
      const seed = testStoreCount * 6
      const baseWeekly = 100_000 + (testStoreCount % 50) * 1000
      // Each model has a characteristic bias/precision trade-off on the
      // eventual-lift estimate — not just cosmetic labels.
      const modelAdjustment: Record<ForecastingModel, number> = {
        arima: 1.0,
        ets: 0.98,
        prophet: 1.02,
        lightgbm: 1.05,
        xgboost: 1.04,
        random_forest: 0.97,
        var: 1.01,
        dynamic_regression: 1.03,
      }
      const eventualLift = (0.02 + Math.abs(Math.sin(seed * 0.19)) * 0.025) * modelAdjustment[model]

      const weeklyPoints: WeeklyForecastPoint[] = []
      for (let w = 1; w <= weeksOfFlight; w++) {
        const rampFactor = Math.min(1, w / 13)
        const noise = (Math.abs(Math.sin((seed + w) * 0.41)) - 0.5) * 0.008
        const liftPercent = Math.round((eventualLift * rampFactor + noise) * 10000) / 100
        const predictedBaseline = Math.round(baseWeekly * (1 + Math.sin(w * 0.5) * 0.03))
        const realizedSales = Math.round(predictedBaseline * (1 + liftPercent / 100))
        const incrementalDeltaDollars = realizedSales - predictedBaseline
        const band = Math.round((0.8 + (1 - rampFactor) * 1.2) * 100) / 100
        weeklyPoints.push({
          week: w,
          predictedBaseline,
          realizedSales,
          incrementalDeltaDollars,
          liftPercent,
          ciLoPercent: Math.round((liftPercent - band) * 100) / 100,
          ciHiPercent: Math.round((liftPercent + band) * 100) / 100,
        })
      }

      // Empirical decay curve for the future horizon: lift settles toward a
      // slightly lower steady-state as novelty effects fade.
      const decayFactor = horizonWeeks === 12 ? 0.95 : horizonWeeks === 26 ? 0.88 : 0.8
      const projectedFutureLiftPercent = Math.round(eventualLift * decayFactor * 10000) / 100

      // Full-Fleet Scale Simulator: tiers scale proportionally FROM the
      // actual pilot cohort size, not fixed absolute numbers — 2x, 5x, and
      // 10x the current pilot, so it's genuinely data-driven.
      const fleetTiers = [testStoreCount, testStoreCount * 2, testStoreCount * 5, testStoreCount * 10]
      const fullFleetSimulation: FullFleetSimulationPoint[] = fleetTiers.map((n) => ({
        storeCount: n,
        projectedAnnualLiftDollars: Math.round(baseWeekly * 52 * n * (projectedFutureLiftPercent / 100)),
      }))

      resolve({
        weeklyPoints,
        horizonWeeks,
        model,
        projectedFutureLiftPercent,
        fullFleetSimulation,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. ROI Synthesis — P&L Money Waterfall
// ─────────────────────────────────────────────────────────────────────────────

export interface MoneyWaterfallResult {
  grossIncrementalRevenue: number
  crossCategoryHaloLift: number
  categoryCannibalization: number
  netIncrementalSales: number
  cogs: number
  operationalExecutionCost: number
  finalNetIncrementalMargin: number
  realizedIroas: number
  reconciliationConfirmed: boolean
  ranAtIso: string
}

export function simulateRoiSynthesis(
  testStoreCount: number,
  initiativeCost: number,
  grossMarginPercent: number,
): Promise<MoneyWaterfallResult> {
  return new Promise((resolve) => {
    const delayMs = 1500 + (testStoreCount % 600)
    window.setTimeout(() => {
      const seed = testStoreCount * 9
      const baseWeeklySales = 100_000 * testStoreCount
      const liftPercent = 0.02 + Math.abs(Math.sin(seed * 0.27)) * 0.02
      const grossIncrementalRevenue = Math.round(baseWeeklySales * 52 * liftPercent)
      const crossCategoryHaloLift = Math.round(grossIncrementalRevenue * (0.05 + Math.abs(Math.cos(seed * 0.4)) * 0.06))
      const categoryCannibalization = -Math.round(grossIncrementalRevenue * (0.03 + Math.abs(Math.sin(seed * 0.6)) * 0.05))
      const netIncrementalSales = grossIncrementalRevenue + crossCategoryHaloLift + categoryCannibalization
      const cogs = -Math.round(netIncrementalSales * (1 - grossMarginPercent))
      const operationalExecutionCost = -Math.round(initiativeCost)
      const finalNetIncrementalMargin = netIncrementalSales + cogs + operationalExecutionCost
      const realizedIroas = initiativeCost > 0 ? Math.round((finalNetIncrementalMargin / initiativeCost) * 100) / 100 : 0

      resolve({
        grossIncrementalRevenue,
        crossCategoryHaloLift,
        categoryCannibalization,
        netIncrementalSales,
        cogs,
        operationalExecutionCost,
        finalNetIncrementalMargin,
        realizedIroas,
        reconciliationConfirmed: true,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. Simpson's Paradox & Heterogeneity Checker
// ─────────────────────────────────────────────────────────────────────────────

export interface SubgroupLift {
  dimension: 'format' | 'size' | 'climate' | 'gold_tier'
  segment: string
  liftPercent: number
}

export interface SimpsonsParadoxResult {
  overallLiftPercent: number
  subgroups: SubgroupLift[]
  paradoxDetected: boolean
  paradoxSegment: string | null
  ranAtIso: string
}

const FORMAT_SEGMENTS = ['Urban', 'Suburban', 'Rural']
const SIZE_SEGMENTS = ['Small', 'Medium', 'Large']
const CLIMATE_SEGMENTS = ['Cold', 'Temperate', 'Hot']
const GOLD_TIER_SEGMENTS = ['Tier 1', 'Tier 2', 'Tier 3']

export function simulateSimpsonsParadoxCheck(testStoreCount: number): Promise<SimpsonsParadoxResult> {
  return new Promise((resolve) => {
    const delayMs = 1400 + (testStoreCount % 600)
    window.setTimeout(() => {
      const seed = testStoreCount * 8
      const overallLiftPercent = Math.round((1.5 + Math.abs(Math.sin(seed * 0.23)) * 1.5) * 100) / 100

      const subgroups: SubgroupLift[] = []
      const dims: { dimension: 'format' | 'size' | 'climate' | 'gold_tier'; segments: string[] }[] = [
        { dimension: 'format', segments: FORMAT_SEGMENTS },
        { dimension: 'size', segments: SIZE_SEGMENTS },
        { dimension: 'climate', segments: CLIMATE_SEGMENTS },
        { dimension: 'gold_tier', segments: GOLD_TIER_SEGMENTS },
      ]

      // A genuine Simpson's Paradox should be a notable, occasional finding —
      // not something that shows up on every single run. ~25% of experiments
      // get a deliberately-injected negative subgroup; the rest vary normally.
      const spA = Math.abs(Math.cos(seed * 0.13))
      const spB = Math.abs(Math.sin(seed * 0.29 + 1.1))
      const shouldHaveParadox = spA * spB > 0.65
      const paradoxDimIdx = Math.floor(seed / 7) % 4
      const paradoxSegIdx = Math.floor(seed / 4) % 3

      dims.forEach((d, dimIdx) => {
        d.segments.forEach((seg, segIdx) => {
          const isParadoxCell = shouldHaveParadox && dimIdx === paradoxDimIdx && segIdx === paradoxSegIdx
          const variation = (Math.abs(Math.cos((seed + dimIdx * 7 + segIdx * 3) * 0.5)) - 0.5) * 3
          const liftPercent = isParadoxCell
            ? Math.round((-0.5 - Math.abs(variation)) * 100) / 100
            : Math.round((overallLiftPercent + variation) * 100) / 100
          subgroups.push({ dimension: d.dimension, segment: seg, liftPercent })
        })
      })

      const paradoxCell = subgroups.find((s) => s.liftPercent < 0)
      const paradoxDetected = !!paradoxCell && overallLiftPercent > 0

      resolve({
        overallLiftPercent,
        subgroups,
        paradoxDetected,
        paradoxSegment: paradoxCell ? `${paradoxCell.segment} (${paradoxCell.dimension})` : null,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. Learnings & Meta-Analysis Repository
// ─────────────────────────────────────────────────────────────────────────────

export type ArchetypeCategory = 'Labor & Staffing' | 'Store Format & Remodel' | 'Merchandising & Assortment' | 'Pricing & Promo'

export interface PastExperimentRecord {
  name: string
  archetype: ArchetypeCategory
  netLiftPercent: number
  iroas: number
  dateCompleted: string
  designHash: string
}

export const PAST_EXPERIMENTS_DB: PastExperimentRecord[] = [
  { name: 'Paint-and-Powder Store Remodel (Wave 2)', archetype: 'Store Format & Remodel', netLiftPercent: 1.4, iroas: 2.9, dateCompleted: '2026-10-15', designHash: '0x7A2C91F0B3D4E812...' },
]

export function searchPastExperiments(archetype: ArchetypeCategory | 'all', query: string): PastExperimentRecord[] {
  return PAST_EXPERIMENTS_DB.filter((e) => {
    const matchesArchetype = archetype === 'all' || e.archetype === archetype
    const matchesQuery = query.trim() === '' || e.name.toLowerCase().includes(query.trim().toLowerCase())
    return matchesArchetype && matchesQuery
  })
}

export function metaAnalysisSummaryFor(archetype: ArchetypeCategory): string {
  const records = PAST_EXPERIMENTS_DB.filter((e) => e.archetype === archetype)
  if (records.length === 0) return `No past ${archetype} experiments on record yet.`
  const avgLift = records.reduce((sum, r) => sum + r.netLiftPercent, 0) / records.length
  const avgIroas = records.reduce((sum, r) => sum + r.iroas, 0) / records.length
  return `Across ${records.length} past ${archetype.toLowerCase()} experiment${records.length > 1 ? 's' : ''}, average net lift was ${avgLift >= 0 ? '+' : ''}${avgLift.toFixed(2)}% with a ${avgIroas.toFixed(1)}x iROAS.`
}
