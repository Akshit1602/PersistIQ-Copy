/**
 * Store Channel — Initiative Setup & Benchmarking: Rollout & Store Targeting Step
 *
 * New step inserted between Metrics and Power for the Store channel only:
 *   Section 1: Rollout Scope (master toggle — partial vs fleet-wide)
 *   Section 2: Treatment Group Filters (partial rollout only)
 *   Section 3: Deployment Timing (partial rollout only — staggered waves)
 *   Section 4: Intelligent Control Selection (AI action: DTW auto-match)
 *   Section 5: Match Validation (dynamic outputs: SMD proof)
 *
 * Used by HypothesisValidatorPanel.tsx when channel === 'store', inserted as
 * the new step 4 (Power moves to step 5, Review to step 6 for this channel).
 */

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: Rollout Scope
// ═══════════════════════════════════════════════════════════════════════════════

export type RolloutScope = 'partial_rollout' | 'fleet_wide_rollout'

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: Treatment Group Filters
// ═══════════════════════════════════════════════════════════════════════════════

export type StoreSizeFilter = 'under_5k' | '5k_to_10k' | 'over_10k'
export type DemographicsFilter = 'urban' | 'suburban' | 'rural'
export type GoldTier = 'tier_1' | 'tier_2' | 'tier_3'

export const STORE_SIZE_OPTIONS: { value: StoreSizeFilter; label: string }[] = [
  { value: 'under_5k', label: '< 5,000 sq ft' },
  { value: '5k_to_10k', label: '5,000 – 10,000 sq ft' },
  { value: 'over_10k', label: '> 10,000 sq ft' },
]

export const DEMOGRAPHICS_OPTIONS: { value: DemographicsFilter; label: string }[] = [
  { value: 'urban', label: 'Urban' },
  { value: 'suburban', label: 'Suburban' },
  { value: 'rural', label: 'Rural' },
]

export const GOLD_TIER_OPTIONS: { value: GoldTier; label: string; hint: string }[] = [
  { value: 'tier_1', label: 'Tier 1', hint: 'Top-performing operational quality' },
  { value: 'tier_2', label: 'Tier 2', hint: 'Mid-band operational quality' },
  { value: 'tier_3', label: 'Tier 3', hint: 'Below-target operational quality' },
]

export type IncomeDecile = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10
export type FamilySizeBand = 'single_or_couple' | 'small_family' | 'large_family'
export type VolumeDecile = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10

export const FAMILY_SIZE_OPTIONS: { value: FamilySizeBand; label: string }[] = [
  { value: 'single_or_couple', label: 'Single / Couple (1-2)' },
  { value: 'small_family', label: 'Small Family (3-4)' },
  { value: 'large_family', label: 'Large Family (5+)' },
]

export interface TreatmentGroupFilters {
  targetStoreCount: number
  storeSize: StoreSizeFilter
  demographics: DemographicsFilter
  goldTiers: GoldTier[]
  incomeDecile: IncomeDecile
  familySize: FamilySizeBand
  registerCount: number
  volumeDecile: VolumeDecile
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: Deployment Timing
// ═══════════════════════════════════════════════════════════════════════════════

export type DeploymentTiming = 'single_wave' | 'staggered_waves'

export interface PhasedWave {
  waveId: number
  storeCount: number
  launchFiscalWeek: number
}

export interface DeploymentSchedule {
  timing: DeploymentTiming
  numberOfWaves: number      // 2–5, only meaningful when staggered
  weeksBetweenWaves: number  // 1–4, only meaningful when staggered
  waves: PhasedWave[]        // the Phased Rollout Matrix — auto-generated, user-editable
}

/** Auto-generates an even Phased Rollout Matrix from wave count/spacing —
 * the starting point users then fine-tune per wave. */
export function generateWaveMatrix(
  numberOfWaves: number,
  weeksBetweenWaves: number,
  totalStoreCount: number,
  startFiscalWeek = 1,
): PhasedWave[] {
  const base = Math.floor(totalStoreCount / numberOfWaves)
  const remainder = totalStoreCount - base * numberOfWaves
  return Array.from({ length: numberOfWaves }, (_, i) => ({
    waveId: i + 1,
    storeCount: base + (i < remainder ? 1 : 0), // distribute any remainder across the first waves
    launchFiscalWeek: startFiscalWeek + i * weeksBetweenWaves,
  }))
}

/** Staggered deployment automatically recommends Staggered DiD
 * (Callaway & Sant'Anna) downstream in the Causal Inference Engine, since a
 * single static estimator can't correctly handle multi-wave adoption. */
export const STAGGERED_ESTIMATOR_RECOMMENDATION = 'staggered_did' as const

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4 + 5: Control Group Methodology, AI Matching & Validation
// ═══════════════════════════════════════════════════════════════════════════════

export type ControlMethod = 'manual_upload' | 'pure_randomized' | 'ai_twin_matching' | 'penalized_synthetic_control'

export const CONTROL_METHOD_OPTIONS: {
  value: ControlMethod
  label: string
  description: string
}[] = [
  {
    value: 'manual_upload',
    label: 'Manual Store Upload',
    description: 'Upload a CSV of exact store IDs to use as controls.',
  },
  {
    value: 'pure_randomized',
    label: 'Pure Randomized Control',
    description: 'System randomly picks stores within the same G.O.L.D. tier.',
  },
  {
    value: 'ai_twin_matching',
    label: 'AI-Assisted Twin Matching (Recommended)',
    description: 'Uses Dynamic Time Warping to find historical sales twins.',
  },
  {
    value: 'penalized_synthetic_control',
    label: 'Penalized Synthetic Control',
    description: 'Builds a weighted composite control per treated store, penalized to avoid interpolation bias (e.g. never averaging a flagship + rural store to fake a mid-tier twin).',
  },
]

export interface ControlMatchResult {
  treatmentGroupSize: number
  controlGroupSize: number
  smd: number
  matchedAtIso: string
  /** Composite distance breakdown (replaces plain nearest-neighbor matching) */
  dtwComponent?: number
  mahalanobisComponent?: number
  spilloverRisk?: number
  compositeDistance?: number
}

export interface SpatialStratificationFilters {
  driveTimeExclusionMiles: number
  excludeNewStores: boolean       // stores open < 12 months
  excludeScheduledRemodels: boolean
}

export const SPATIAL_STRATIFICATION_DEFAULTS: SpatialStratificationFilters = {
  driveTimeExclusionMiles: 15,
  excludeNewStores: true,
  excludeScheduledRemodels: true,
}

/**
 * Mocked DTW auto-match: deterministic given the same inputs (not truly
 * random per click), returns after a short delay to drive the loading state.
 * A real deployment would call the backend, which runs DTW against
 * dev.matchview_store.store_performance_weekly pre-period sales curves.
 */
export function simulateControlMatching(
  filters: TreatmentGroupFilters,
): Promise<ControlMatchResult> {
  return new Promise((resolve) => {
    const delayMs = 900 + (filters.targetStoreCount % 400)
    window.setTimeout(() => {
      // Deterministic pseudo-random SMD seeded off the inputs, biased low
      // (a good match) since AI-assisted twin matching is the recommended path.
      const seed =
        filters.targetStoreCount +
        filters.goldTiers.length * 37 +
        filters.storeSize.length +
        filters.demographics.length
      const pseudoRandom = Math.abs(Math.sin(seed)) // 0–1, deterministic
      const smd = Math.round((0.015 + pseudoRandom * 0.07) * 1000) / 1000 // ~0.015–0.085

      // Composite distance: DTW (curve shape) + Mahalanobis (structural
      // covariates) + spillover risk (shared trade-area exposure) — replaces
      // basic nearest-neighbor matching with a weighted combination.
      const dtwComponent = Math.round((0.05 + pseudoRandom * 0.15) * 1000) / 1000
      const mahalanobisComponent = Math.round((0.03 + Math.abs(Math.cos(seed * 1.1)) * 0.12) * 1000) / 1000
      const spilloverRisk = Math.round(Math.abs(Math.sin(seed * 0.6)) * 0.2 * 1000) / 1000
      const compositeDistance = Math.round((0.5 * dtwComponent + 0.35 * mahalanobisComponent + 0.15 * spilloverRisk) * 1000) / 1000

      resolve({
        treatmentGroupSize: filters.targetStoreCount,
        controlGroupSize: filters.targetStoreCount, // 1:1 matched pool
        smd,
        matchedAtIso: new Date().toISOString(),
        dtwComponent,
        mahalanobisComponent,
        spilloverRisk,
        compositeDistance,
      })
    }, delayMs)
  })
}

/**
 * Penalized synthetic control: builds a weighted composite donor pool per
 * treated store, with a penalty term discouraging extreme-weight
 * interpolation (e.g. never averaging a flagship + rural store to fake a
 * mid-tier twin — weights are shrunk toward donors that are individually
 * close, not just collectively averaging to the right number).
 */
export function simulateSyntheticControl(
  filters: TreatmentGroupFilters,
): Promise<ControlMatchResult> {
  return new Promise((resolve) => {
    const delayMs = 1000 + (filters.targetStoreCount % 400)
    window.setTimeout(() => {
      const seed = filters.targetStoreCount * 7 + filters.goldTiers.length * 19
      const pseudoRandom = Math.abs(Math.sin(seed * 0.9))
      // Penalization trades a touch of raw balance for much lower
      // interpolation-bias risk — SMD is comparable to AI twin matching.
      const smd = Math.round((0.02 + pseudoRandom * 0.08) * 1000) / 1000
      const dtwComponent = Math.round((0.04 + pseudoRandom * 0.1) * 1000) / 1000
      const mahalanobisComponent = Math.round((0.02 + Math.abs(Math.cos(seed * 0.7)) * 0.08) * 1000) / 1000
      const spilloverRisk = Math.round(Math.abs(Math.sin(seed * 0.4)) * 0.1 * 1000) / 1000
      const compositeDistance = Math.round((0.5 * dtwComponent + 0.35 * mahalanobisComponent + 0.15 * spilloverRisk) * 1000) / 1000

      resolve({
        treatmentGroupSize: filters.targetStoreCount,
        controlGroupSize: filters.targetStoreCount,
        smd,
        matchedAtIso: new Date().toISOString(),
        dtwComponent,
        mahalanobisComponent,
        spilloverRisk,
        compositeDistance,
      })
    }, delayMs)
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Full Rollout & Store Targeting State
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Mocked pure-randomized control: draws stores from the same G.O.L.D. tier
 * at random (no curve-shape matching). Generally solid balance since it's
 * stratified by tier, but — being pure random rather than DTW-matched — the
 * SMD distribution is centered a bit higher/wider than AI-assisted twin
 * matching's.
 */
export function simulateRandomizedControl(
  filters: TreatmentGroupFilters,
): Promise<ControlMatchResult> {
  return new Promise((resolve) => {
    const delayMs = 500 + (filters.targetStoreCount % 250)
    window.setTimeout(() => {
      const seed =
        filters.targetStoreCount * 3 +
        filters.goldTiers.length * 53 +
        filters.storeSize.length * 7 +
        filters.demographics.length * 11
      const pseudoRandom = Math.abs(Math.cos(seed)) // 0–1, deterministic
      const smd = Math.round((0.03 + pseudoRandom * 0.13) * 1000) / 1000 // ~0.03–0.16

      resolve({
        treatmentGroupSize: filters.targetStoreCount,
        controlGroupSize: filters.targetStoreCount,
        smd,
        matchedAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Manual Store Upload — CSV parsing + validation
// ═══════════════════════════════════════════════════════════════════════════════

export interface ManualUploadState {
  fileName: string | null
  storeIds: string[]
  error: string | null
}

export const EMPTY_MANUAL_UPLOAD: ManualUploadState = {
  fileName: null,
  storeIds: [],
  error: null,
}

/**
 * Parses a CSV of store IDs — accepts either a bare list (one ID per line,
 * optional header row like "store_id") or a single-column extract from a
 * larger export. Very permissive: strips quotes/whitespace, dedupes, and
 * skips a header row if the first line doesn't look like a store ID.
 */
export function parseManualStoreCsv(csvText: string): { storeIds: string[]; error: string | null } {
  const lines = csvText
    .split(/\r?\n/)
    .map((l) => l.split(',')[0]?.trim().replace(/^"|"$/g, ''))
    .filter((l) => l.length > 0)

  if (lines.length === 0) {
    return { storeIds: [], error: 'The file is empty or could not be read.' }
  }

  const looksLikeHeader = /^(store[_\s]?id|id)$/i.test(lines[0])
  const rows = looksLikeHeader ? lines.slice(1) : lines
  const storeIds = Array.from(new Set(rows))

  if (storeIds.length === 0) {
    return { storeIds: [], error: 'No store IDs found in the file.' }
  }
  return { storeIds, error: null }
}

/**
 * Validates an uploaded control list against the treatment group. Since this
 * is a frontend prototype without a live store_master lookup, the SMD here
 * is a deterministic simulation seeded off the uploaded list — a real
 * deployment would compute it against actual store covariates.
 */
export function simulateManualUploadValidation(
  storeIds: string[],
  filters: TreatmentGroupFilters,
): Promise<ControlMatchResult> {
  return new Promise((resolve) => {
    window.setTimeout(() => {
      const seed = storeIds.length * 17 + storeIds.join('').length
      const pseudoRandom = Math.abs(Math.sin(seed * 0.7))
      // Manual selection has the widest SMD range — no algorithmic balancing.
      const smd = Math.round((0.02 + pseudoRandom * 0.22) * 1000) / 1000 // ~0.02–0.24

      resolve({
        treatmentGroupSize: filters.targetStoreCount,
        controlGroupSize: storeIds.length,
        smd,
        matchedAtIso: new Date().toISOString(),
      })
    }, 400)
  })
}

export interface StoreRolloutTargeting {
  rolloutScope: RolloutScope
  treatmentFilters: TreatmentGroupFilters
  deploymentSchedule: DeploymentSchedule
  controlMethod: ControlMethod
  matchResult: ControlMatchResult | null
  isMatching: boolean
  manualUpload: ManualUploadState
  spatialFilters: SpatialStratificationFilters
}

export const STORE_ROLLOUT_DEFAULTS: StoreRolloutTargeting = {
  rolloutScope: 'partial_rollout',
  treatmentFilters: {
    targetStoreCount: 500,
    storeSize: '5k_to_10k',
    demographics: 'suburban',
    goldTiers: ['tier_1', 'tier_2'],
    incomeDecile: 5,
    familySize: 'small_family',
    registerCount: 4,
    volumeDecile: 5,
  },
  deploymentSchedule: {
    timing: 'single_wave',
    numberOfWaves: 3,
    weeksBetweenWaves: 2,
    waves: generateWaveMatrix(3, 2, 500),
  },
  controlMethod: 'ai_twin_matching',
  matchResult: null,
  isMatching: false,
  manualUpload: EMPTY_MANUAL_UPLOAD,
  spatialFilters: SPATIAL_STRATIFICATION_DEFAULTS,
}

export const WAVE_COUNT_OPTIONS = [2, 3, 4, 5]
export const WEEKS_BETWEEN_WAVES_OPTIONS = [1, 2, 3, 4]

export const SMD_TARGET_THRESHOLD = 0.1

/** Validation gate for the Rollout & Store Targeting step */
export function isStoreRolloutValid(rollout: StoreRolloutTargeting): boolean {
  if (rollout.rolloutScope === 'fleet_wide_rollout') return true

  const { treatmentFilters, deploymentSchedule } = rollout
  if (treatmentFilters.targetStoreCount <= 0 || treatmentFilters.targetStoreCount > 100000) return false
  if (treatmentFilters.goldTiers.length === 0) return false

  if (deploymentSchedule.timing === 'staggered_waves') {
    if (!WAVE_COUNT_OPTIONS.includes(deploymentSchedule.numberOfWaves)) return false
    if (!WEEKS_BETWEEN_WAVES_OPTIONS.includes(deploymentSchedule.weeksBetweenWaves)) return false
  }

  return true
}
