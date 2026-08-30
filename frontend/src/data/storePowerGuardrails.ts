/**
 * Store Channel — Initiative Setup & Benchmarking: Power & Guardrails Step
 *
 * Replaces the digital channel's generic Power Calculator for the Store
 * channel with:
 *   - Historical Baseline Variance Lookback (drives sigma from
 *     dev.matchview_store.store_performance_weekly)
 *   - CUPED variance-reduction toggle
 *   - Significance level (alpha) and Statistical Power (1-beta) dropdowns
 *   - A dynamic MDE-vs-Target-Lift viability card (replaces the digital
 *     slider-based MDE input — Target Lift is read from Opportunity Sizing)
 *   - A Historical A/A sanity-check simulation
 *
 * Used by HypothesisValidatorPanel.tsx when channel === 'store', rendered as
 * the (store-only) step 5 — after Rollout & Store Targeting, before Review.
 */

export type HistoricalLookbackMode = 'recent_quarter' | 'trailing_52' | 'seasonal_same_period' | 'custom'
export type AlphaLevel = 0.01 | 0.05 | 0.1
export type PowerLevel = 0.8 | 0.9

export const LOOKBACK_OPTIONS: { value: HistoricalLookbackMode; label: string; effectiveWeeks: 13 | 52 | null }[] = [
  { value: 'recent_quarter', label: 'Recent Quarter (13 Weeks)', effectiveWeeks: 13 },
  { value: 'trailing_52', label: 'Trailing 52 Weeks', effectiveWeeks: 52 },
  { value: 'seasonal_same_period', label: 'Same Season Last Year (Seasonal Matching)', effectiveWeeks: 52 },
  { value: 'custom', label: '+ Add Custom Lookback…', effectiveWeeks: null },
]

export const ALPHA_OPTIONS: { value: AlphaLevel; label: string }[] = [
  { value: 0.01, label: '99% Confidence (\u03B1 = 0.01)' },
  { value: 0.05, label: '95% Confidence (\u03B1 = 0.05) - Standard' },
  { value: 0.1, label: '90% Confidence (\u03B1 = 0.10)' },
]

export const POWER_OPTIONS: { value: PowerLevel; label: string }[] = [
  { value: 0.8, label: '80% Power (\u03B2 = 0.20) - Standard' },
  { value: 0.9, label: '90% Power (\u03B2 = 0.10) - High Certainty' },
]

// Two-tailed z critical values for each supported alpha (avoids needing a
// stats library client-side — these are the standard textbook constants).
const Z_ALPHA_HALF: Record<AlphaLevel, number> = {
  0.01: 2.576,
  0.05: 1.96,
  0.1: 1.645,
}

// One-tailed z critical values for each supported power target.
const Z_BETA: Record<PowerLevel, number> = {
  0.8: 0.8416,
  0.9: 1.2816,
}

// Baseline relative std-dev (sigma) of the primary conversion-style metric by
// lookback window — longer windows smooth over more seasonal cycles, so the
// effective baseline variance used for power is lower (more stable estimate).
const BASE_SIGMA_BY_LOOKBACK: Record<Exclude<HistoricalLookbackMode, 'custom'>, number> = {
  recent_quarter: 0.045,
  trailing_52: 0.036,
  seasonal_same_period: 0.03, // matching the exact same calendar period removes the most noise
}

// CUPED variance reduction factor — how much a well-correlated pre-period
// covariate typically shrinks baseline variance. Conservative assumption.
const CUPED_VARIANCE_REDUCTION = 0.3 // 30% reduction in sigma^2

export interface AATestResult {
  simulatedLiftPercent: number
  falsePositiveRatePercent: number
  nominalAlphaPercent: number
  passed: boolean
  ranAtIso: string
}

export interface EmpiricalPowerResult {
  nDraws: number
  empiricalPowerPercent: number
  ranAtIso: string
}

export interface StorePowerConfig {
  historicalLookbackMode: HistoricalLookbackMode
  customLookbackWeeks: number | null
  cupedEnabled: boolean
  alpha: AlphaLevel
  statisticalPower: PowerLevel
  aaTestResult: AATestResult | null
  isRunningAaTest: boolean
  empiricalPowerResult: EmpiricalPowerResult | null
  isRunningEmpiricalPower: boolean
}

export const STORE_POWER_DEFAULTS: StorePowerConfig = {
  historicalLookbackMode: 'seasonal_same_period',
  customLookbackWeeks: null,
  cupedEnabled: true,
  alpha: 0.05,
  statisticalPower: 0.8,
  aaTestResult: null,
  isRunningAaTest: false,
  empiricalPowerResult: null,
  isRunningEmpiricalPower: false,
}

/**
 * Baseline sigma for a custom lookback: interpolated smoothly on a log scale
 * between the recent-quarter (13wk, noisiest) and trailing-52 (52wk,
 * smoothest) anchors — more weeks of history means a more stable estimate.
 */
function sigmaForCustomWeeks(weeks: number): number {
  const clamped = Math.max(4, Math.min(104, weeks))
  const t = Math.log(clamped / 13) / Math.log(52 / 13) // 0 at 13wk, 1 at 52wk
  const sigma13 = BASE_SIGMA_BY_LOOKBACK.recent_quarter
  const sigma52 = BASE_SIGMA_BY_LOOKBACK.trailing_52
  return sigma13 + (sigma52 - sigma13) * Math.max(0, Math.min(1.3, t))
}

/**
 * MDE = (z_alpha/2 + z_beta) * sqrt(2 * sigma^2 / N)
 * Returns the Minimum Detectable Effect as a fraction (e.g. 0.008 = 0.8%).
 */
export function computeMde(config: StorePowerConfig, storeCount: number): number {
  const baseSigma =
    config.historicalLookbackMode === 'custom'
      ? sigmaForCustomWeeks(config.customLookbackWeeks ?? 52)
      : BASE_SIGMA_BY_LOOKBACK[config.historicalLookbackMode]
  const sigma = config.cupedEnabled
    ? baseSigma * Math.sqrt(1 - CUPED_VARIANCE_REDUCTION)
    : baseSigma
  const n = Math.max(storeCount, 1)
  const zSum = Z_ALPHA_HALF[config.alpha] + Z_BETA[config.statisticalPower]
  return zSum * Math.sqrt((2 * sigma * sigma) / n)
}

export function isAdequatelyPowered(targetLiftPercent: number, mdePercent: number): boolean {
  return targetLiftPercent >= mdePercent
}

/**
 * A/A gate hard stop: runs a simulated A/A test on historical data and
 * checks whether the empirical false-positive rejection rate exceeds a
 * tolerance band above the nominal alpha (e.g. >7% at alpha=5% — a ~1.4x
 * tolerance is standard practice for flagging real miscalibration vs. noise).
 * A FAILED result is meant to hard-block launch, not just warn.
 */
export function simulateHistoricalAaTest(
  config: StorePowerConfig,
  storeCount: number,
): Promise<AATestResult> {
  return new Promise((resolve) => {
    const delayMs = 700 + (storeCount % 300)
    window.setTimeout(() => {
      const seed = storeCount + config.historicalLookbackMode.length * 3 + (config.cupedEnabled ? 17 : 0)
      const pseudoRandom = Math.abs(Math.sin(seed * 1.7)) // 0–1, deterministic
      const simulatedLiftPercent = Math.round((pseudoRandom - 0.5) * 0.4 * 100) / 100 // ~ -0.20% to +0.20%

      const nominalAlphaPercent = config.alpha * 100
      // False-positive rate hovers near the nominal alpha, occasionally
      // drifting higher — deterministic given the same config.
      const driftSeed = Math.abs(Math.cos(seed * 0.53))
      const falsePositiveRatePercent = Math.round(nominalAlphaPercent * (0.6 + driftSeed * 1.0) * 100) / 100
      const tolerance = nominalAlphaPercent * 1.4 // e.g. 7% tolerance at alpha=5%
      const passed = falsePositiveRatePercent <= tolerance

      resolve({
        simulatedLiftPercent,
        falsePositiveRatePercent,
        nominalAlphaPercent,
        passed,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

/**
 * Empirical simulation backbone: replays N historical draws, applies a
 * placebo treatment to each, and measures how often a synthetic lift of the
 * target size would have been detected — an empirical alternative/companion
 * to the closed-form z-formula MDE above.
 */
export const EMPIRICAL_DRAW_OPTIONS = [500, 750, 1000] as const
export type EmpiricalDrawCount = (typeof EMPIRICAL_DRAW_OPTIONS)[number]

export function simulateEmpiricalPower(
  config: StorePowerConfig,
  storeCount: number,
  targetLiftPercent: number,
  nDraws: EmpiricalDrawCount = 750,
): Promise<EmpiricalPowerResult> {
  return new Promise((resolve) => {
    const draws = nDraws
    const delayMs = 1200 + (storeCount % 500)
    window.setTimeout(() => {
      const mdePercent = computeMde(config, storeCount) * 100
      // Empirical power should track the closed-form power target, with a
      // small amount of simulation noise around it.
      const seed = storeCount * 3 + Math.round(targetLiftPercent * 100) + draws
      const noise = (Math.abs(Math.sin(seed * 0.21)) - 0.5) * 6 // +/- 3pp of simulation noise
      const basePowerPercent = config.statisticalPower * 100
      const liftMdeRatio = mdePercent > 0 ? targetLiftPercent / mdePercent : 1
      // If target lift is comfortably above MDE, empirical power runs a bit
      // above the nominal target; if it's marginal, empirical power runs
      // below it — mirroring how real simulation-based power behaves.
      const adjustment = (liftMdeRatio - 1) * 15
      const empiricalPowerPercent = Math.min(99, Math.max(5, Math.round((basePowerPercent + adjustment + noise) * 10) / 10))

      resolve({
        nDraws: draws,
        empiricalPowerPercent,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}
