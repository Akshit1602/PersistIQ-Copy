/**
 * Store Channel — Live Execution Monitoring (3 sub-modules)
 *
 *   1. Store Feed & Execution Diagnostics (relabels 'experiment-analysis')
 *   2. Peeking Protection & Futility (relabels 'health-monitor')
 *   3. In-Flight Lift Trajectory (relabels 'sequential-testing')
 */

// ─────────────────────────────────────────────────────────────────────────────
// 1. Store Feed & Execution Diagnostics
// ─────────────────────────────────────────────────────────────────────────────

export interface StoreQuarantineFlag {
  storeId: string
  reason: string
}

export interface StoreFeedChecksToggle {
  runPosIngestion: boolean
  runStockoutFilter: boolean
  runExecutionRate: boolean
}

export const STORE_FEED_CHECKS_DEFAULTS: StoreFeedChecksToggle = {
  runPosIngestion: true,
  runStockoutFilter: true,
  runExecutionRate: true,
}

export interface StoreFeedDiagnosticsResult {
  posIngestionPercent: number | null
  storesWithDataGaps: number
  stockoutFlags: StoreQuarantineFlag[] | null
  operationalExecutionRatePercent: number | null
  quarantineCandidates: StoreQuarantineFlag[] | null
  ranAtIso: string
}

export function simulateStoreFeedDiagnostics(
  testStoreCount: number,
  checks: StoreFeedChecksToggle,
): Promise<StoreFeedDiagnosticsResult> {
  return new Promise((resolve) => {
    const delayMs = 1000 + (testStoreCount % 500)
    window.setTimeout(() => {
      const seed = testStoreCount * 3

      let posIngestionPercent: number | null = null
      let storesWithDataGaps = 0
      if (checks.runPosIngestion) {
        posIngestionPercent = Math.round((98 + Math.abs(Math.sin(seed * 0.3)) * 2) * 10) / 10
        storesWithDataGaps = Math.max(0, Math.round(testStoreCount * (1 - posIngestionPercent / 100)))
      }

      let stockoutFlags: StoreQuarantineFlag[] | null = null
      if (checks.runStockoutFilter) {
        const nStockoutFlags = Math.round(Math.abs(Math.cos(seed * 0.5)) * 4)
        stockoutFlags = Array.from({ length: nStockoutFlags }, (_, i) => ({
          storeId: `S${(1000 + i * 7).toString()}`,
          reason: 'Primary test SKU out-of-stock > 24 hours',
        }))
      }

      let operationalExecutionRatePercent: number | null = null
      let quarantineCandidates: StoreQuarantineFlag[] | null = null
      if (checks.runExecutionRate) {
        operationalExecutionRatePercent = Math.round((88 + Math.abs(Math.sin(seed * 0.7)) * 10) * 10) / 10
        const nQuarantine = operationalExecutionRatePercent < 92 ? Math.round(Math.abs(Math.cos(seed * 0.9)) * 3) : 0
        quarantineCandidates = Array.from({ length: nQuarantine }, (_, i) => ({
          storeId: `S${(2000 + i * 11).toString()}`,
          reason: 'Below execution threshold (required cashier hours not logged)',
        }))
      }

      resolve({
        posIngestionPercent,
        storesWithDataGaps,
        stockoutFlags,
        operationalExecutionRatePercent,
        quarantineCandidates,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. Peeking Protection & Futility
// ─────────────────────────────────────────────────────────────────────────────

export interface PeekingProtectionResult {
  currentWeek: number
  anytimeValidPValue: number
  currentZScore: number
  probabilityOfClearingMde: number
  futilityTriggered: boolean
  ranAtIso: string
}

export function simulatePeekingProtection(
  testStoreCount: number,
  currentWeek: number,
): Promise<PeekingProtectionResult> {
  return new Promise((resolve) => {
    const delayMs = 900 + (testStoreCount % 400)
    window.setTimeout(() => {
      const seed = testStoreCount * 2 + currentWeek * 13
      const pseudoRandom = Math.abs(Math.sin(seed * 0.44))
      const currentZScore = Math.round((pseudoRandom * 2.2) * 100) / 100
      const anytimeValidPValue = Math.round(Math.max(0.001, (1 - pseudoRandom) * 0.3) * 1000) / 1000

      // Signal strength is fixed per-experiment (independent of week) — most
      // experiments are healthy and trend toward higher power over time, but
      // a genuine minority are underpowered/futile and should show declining
      // probability as weeks pass without the lift materializing.
      const expSeed = testStoreCount * 7
      const signalStrength = Math.abs(Math.sin(expSeed * 0.37))
      let probabilityOfClearingMde: number
      if (signalStrength < 0.18) {
        probabilityOfClearingMde = Math.max(1, 14 - currentWeek * 2.8)
      } else {
        const trendFactor = Math.min(1, currentWeek / 8)
        probabilityOfClearingMde = Math.min(97, signalStrength * 55 + trendFactor * 40)
      }
      probabilityOfClearingMde = Math.round(probabilityOfClearingMde * 10) / 10
      const futilityTriggered = currentWeek >= 2 && probabilityOfClearingMde < 5

      resolve({
        currentWeek,
        anytimeValidPValue,
        currentZScore,
        probabilityOfClearingMde,
        futilityTriggered,
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. In-Flight Lift Trajectory
// ─────────────────────────────────────────────────────────────────────────────

export interface WeeklyLiftPoint {
  week: number
  treatedSales: number
  controlSales: number
  liftPercent: number
}

export interface EmergingMetricsSummary {
  primaryKpiDirectionalLiftPercent: number
  secondaryKpiDirectionalLiftPercent: number
  guardrailStatus: 'within_normal_range' | 'watch'
}

export interface LiftTrajectoryResult {
  weeklyPoints: WeeklyLiftPoint[]
  rampHorizonWeeks: 4 | 13
  emergingMetrics: EmergingMetricsSummary
  ranAtIso: string
}

export function simulateLiftTrajectory(
  testStoreCount: number,
  weeksElapsed: number,
  rampHorizonWeeks: 4 | 13 = 13,
): Promise<LiftTrajectoryResult> {
  return new Promise((resolve) => {
    const delayMs = 1100 + (testStoreCount % 500)
    window.setTimeout(() => {
      const seed = testStoreCount * 4
      const baseWeekly = 100_000 + (testStoreCount % 50) * 1000
      const targetLift = 0.02 + (Math.abs(Math.sin(seed * 0.2)) * 0.02) // ~2-4% eventual lift

      const weeklyPoints: WeeklyLiftPoint[] = []
      for (let w = 1; w <= weeksElapsed; w++) {
        const rampFactor = Math.min(1, w / rampHorizonWeeks)
        const noise = (Math.abs(Math.sin((seed + w) * 0.37)) - 0.5) * 0.01
        const liftPercent = Math.round((targetLift * rampFactor + noise) * 10000) / 100
        const controlSales = Math.round(baseWeekly * (1 + Math.sin(w * 0.5) * 0.03))
        const treatedSales = Math.round(controlSales * (1 + liftPercent / 100))
        weeklyPoints.push({ week: w, treatedSales, controlSales, liftPercent })
      }

      const lastLift = weeklyPoints[weeklyPoints.length - 1]?.liftPercent ?? 0
      const guardrailRoll = Math.abs(Math.cos(seed * 0.6))

      resolve({
        weeklyPoints,
        rampHorizonWeeks,
        emergingMetrics: {
          primaryKpiDirectionalLiftPercent: lastLift,
          secondaryKpiDirectionalLiftPercent: Math.round(lastLift * 0.6 * 100) / 100,
          guardrailStatus: guardrailRoll > 0.85 ? 'watch' : 'within_normal_range',
        },
        ranAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}
