/**
 * Store Channel — Balance Diagnostics Module
 *
 * Statistical pre-flight check on the Test-vs-Control cohort produced by
 * Store Matching & Panel Selection: Covariate Balance Check, Parallel
 * Pre-Trends (RMSPE), and Placebo-in-Time (A/A) — proving the control panel
 * is mathematically valid before launch.
 */

export type LookbackWindow = 26 | 52 | 104

export const LOOKBACK_WINDOW_OPTIONS: { value: LookbackWindow; label: string }[] = [
  { value: 26, label: '26 Weeks' },
  { value: 52, label: '52 Weeks (1 Full Year - Recommended for Seasonality)' },
  { value: 104, label: '104 Weeks (2 Years)' },
]

export interface DiagnosticTestsToggle {
  runParallelPreTrends: boolean
  runCovariateBalance: boolean
  runPlaceboInTime: boolean
}

export interface RMSPEResult {
  rmspe: number
  passed: boolean
}

export interface CovariateAttributeBalance {
  name: string
  smd: number
  balanced: boolean
}

export interface CovariateBalanceResult {
  attributes: CovariateAttributeBalance[]
  maxSmd: number
  allBalanced: boolean
}

export interface PlaceboInTimeResult {
  falsePositiveRatePercent: number
  passed: boolean
}

export interface BalanceDiagnosticsRunResult {
  rmspe: RMSPEResult | null
  covariateBalance: CovariateBalanceResult | null
  placeboInTime: PlaceboInTimeResult | null
  overallPassed: boolean
  ranAtIso: string
}

export interface StoreBalanceDiagnosticsState {
  lookbackWeeks: LookbackWindow
  maxSmdThreshold: number
  tests: DiagnosticTestsToggle
  runResult: BalanceDiagnosticsRunResult | null
  isRunning: boolean
}

export const STORE_BALANCE_DIAGNOSTICS_DEFAULTS: StoreBalanceDiagnosticsState = {
  lookbackWeeks: 52,
  maxSmdThreshold: 0.1,
  tests: {
    runParallelPreTrends: true,
    runCovariateBalance: true,
    runPlaceboInTime: true,
  },
  runResult: null,
  isRunning: false,
}

const COVARIATE_ATTRIBUTES = ['Store Size (sq ft)', 'Volume Decile', 'Population Density', 'Pre-Treatment G.O.L.D. Tier']

/**
 * Runs the selected diagnostic tests against the matched cohort. Deterministic
 * given the same inputs — a real deployment would compute these directly
 * against dev.matchview_store.store_performance_weekly for the matched pairs.
 */
export function simulateBalanceDiagnostics(
  state: StoreBalanceDiagnosticsState,
  testStoreCount: number,
): Promise<BalanceDiagnosticsRunResult> {
  return new Promise((resolve) => {
    const delayMs = 1600 + (testStoreCount % 700)
    window.setTimeout(() => {
      const seed = testStoreCount * 5 + state.lookbackWeeks * 3

      let rmspe: RMSPEResult | null = null
      if (state.tests.runParallelPreTrends) {
        const pseudoRandom = Math.abs(Math.sin(seed * 0.41))
        // Longer lookback -> more stable, generally lower RMSPE.
        const lookbackFactor = state.lookbackWeeks === 104 ? 0.8 : state.lookbackWeeks === 52 ? 1.0 : 1.3
        const rmspeValue = Math.round(pseudoRandom * 0.048 * lookbackFactor * 1000) / 1000
        rmspe = { rmspe: rmspeValue, passed: rmspeValue < 0.05 }
      }

      let covariateBalance: CovariateBalanceResult | null = null
      if (state.tests.runCovariateBalance) {
        const attributes: CovariateAttributeBalance[] = COVARIATE_ATTRIBUTES.map((name, i) => {
          const pseudoRandom = Math.abs(Math.cos(seed * (0.3 + i * 0.17)))
          const smd = Math.round(pseudoRandom * 0.08 * 1000) / 1000
          return { name, smd, balanced: smd < state.maxSmdThreshold }
        })
        const maxSmd = Math.max(...attributes.map((a) => a.smd))
        covariateBalance = { attributes, maxSmd, allBalanced: attributes.every((a) => a.balanced) }
      }

      let placeboInTime: PlaceboInTimeResult | null = null
      if (state.tests.runPlaceboInTime) {
        const pseudoRandom = Math.abs(Math.sin(seed * 0.67 + 1.3))
        const falsePositiveRatePercent = Math.round(pseudoRandom * 6 * 100) / 100 // 0-6%
        placeboInTime = { falsePositiveRatePercent, passed: falsePositiveRatePercent < 7 }
      }

      const overallPassed =
        (rmspe?.passed ?? true) && (covariateBalance?.allBalanced ?? true) && (placeboInTime?.passed ?? true)

      resolve({
        rmspe,
        covariateBalance,
        placeboInTime,
        overallPassed,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}
