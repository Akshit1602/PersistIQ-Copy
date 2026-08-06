/**
 * Store Channel — Initiative Setup & Benchmarking: Review & Concurrency Step
 *
 * The final (store-only) step 6:
 *   Section 1: Concurrent Initiative Collision Radar (auto-detected overlap
 *     with other planned store initiatives + a resolution strategy choice)
 *   Section 2: Executive Blueprint Summary (read-only rollup of every prior
 *     step, for a single-screen executive sign-off view)
 *   Section 3: Pre-Flight Launch Sign-Off (owner email, notes, deploy)
 */

export type CollisionHandlingStrategy = 'debias-ml' | 'exclude-colliding-stores' | 'proceed-with-warning'
export type OverlapType = 'remodel' | 'pricing-change' | 'assortment-shift' | 'promo-test'

export interface OverlappingInitiative {
  initiativeId: string
  initiativeName: string
  archetype: string
  impactedStoreCount: number
  overlapType: OverlapType
  startDate: string
  endDate: string
  dosageDescription: string
}

export interface DetectedCollisions {
  totalTargetStores: number
  cleanStoresCount: number
  collidingStoresCount: number
  overlappingInitiatives: OverlappingInitiative[]
}

export interface ConcurrencyReviewState {
  collisionHandlingStrategy: CollisionHandlingStrategy
  selectedInitiativeIds: string[]
  businessOwnerEmail: string
  experimentNotes: string
  isReadyForLaunch: boolean
  detectedCollisions: DetectedCollisions
}

export const EMPTY_DETECTED_COLLISIONS: DetectedCollisions = {
  totalTargetStores: 0,
  cleanStoresCount: 0,
  collidingStoresCount: 0,
  overlappingInitiatives: [],
}

export const STORE_CONCURRENCY_REVIEW_DEFAULTS: ConcurrencyReviewState = {
  collisionHandlingStrategy: 'debias-ml',
  selectedInitiativeIds: [],
  businessOwnerEmail: '',
  experimentNotes: '',
  isReadyForLaunch: false,
  detectedCollisions: EMPTY_DETECTED_COLLISIONS,
}

// ─────────────────────────────────────────────────────────────────────────────
// Collision detection simulation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Other planned/in-flight store initiatives this experiment's target cohort
 * could plausibly overlap with — the same 3 named initiatives from the
 * general store retail MVP scope, playing the role of "already scheduled" programs a
 * new test might collide with.
 */
export const OTHER_PLANNED_INITIATIVES: Omit<OverlappingInitiative, 'impactedStoreCount'>[] = [
  {
    initiativeId: 'INIT-882',
    initiativeName: 'Paint-and-Powder Store Remodel (Wave 2)',
    archetype: 'Archetype B (Condition & Refresh)',
    overlapType: 'remodel',
    startDate: '2026-09-01',
    endDate: '2026-10-15',
    dosageDescription: '$650,000 remodel budget / store',
  },
  {
    initiativeId: 'INIT-904',
    initiativeName: 'Multi-Price Shelf Tagging Pilot',
    archetype: 'Archetype A (Structural & Format)',
    overlapType: 'pricing-change',
    startDate: '2026-08-15',
    endDate: '2026-11-01',
    dosageDescription: '5% avg price delta',
  },
  {
    initiativeId: 'INIT-916',
    initiativeName: 'Dedicated Cashier Staffing Rollout',
    archetype: 'Archetype C (Staffing & Labor)',
    overlapType: 'assortment-shift',
    startDate: '2026-07-20',
    endDate: '2026-09-30',
    dosageDescription: '32 cashier hours / store / week',
  },
]

/**
 * Deterministic (given the same target store count) collision scan — a real
 * deployment would query store_initiative_mapping for active/upcoming
 * initiatives touching the same store_ids. Scales the impacted counts to the
 * actual target cohort size rather than always returning the illustrative
 * 500/350/150 example numbers.
 */
export function detectCollisions(targetStoreCount: number): DetectedCollisions {
  if (targetStoreCount <= 0) return EMPTY_DETECTED_COLLISIONS

  // Fixed, deterministic collision — the same single initiative every time,
  // regardless of store count, so it's consistent everywhere this data is
  // referenced (Review step, Brief Generator, ROI reconciliation, etc.).
  const fixedInitiative = OTHER_PLANNED_INITIATIVES[0]
  const overlapFraction = 0.2 // ~20% of the cohort overlaps with this one fixed initiative

  const impactedStoreCount = Math.max(1, Math.round(targetStoreCount * overlapFraction))
  const overlappingInitiatives: OverlappingInitiative[] = [{ ...fixedInitiative, impactedStoreCount }]

  const collidingStoresCount = Math.min(impactedStoreCount, targetStoreCount)
  const cleanStoresCount = targetStoreCount - collidingStoresCount

  return {
    totalTargetStores: targetStoreCount,
    cleanStoresCount,
    collidingStoresCount,
    overlappingInitiatives,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// UI copy catalog
// ─────────────────────────────────────────────────────────────────────────────

export const COLLISION_STRATEGY_OPTIONS: {
  value: CollisionHandlingStrategy
  label: string
  helper: string
}[] = [
  {
    value: 'debias-ml',
    label: 'Apply Double / Debiased Machine Learning (Recommended)',
    helper: 'Adjusts for overlap noise in post-test analysis without sacrificing store count.',
  },
  {
    value: 'exclude-colliding-stores',
    label: 'Auto-Prune Colliding Stores',
    helper: 'Drops the colliding stores from your test cohort, reducing sample size to the clean count.',
  },
  {
    value: 'proceed-with-warning',
    label: 'Proceed Without Mitigation (High Risk)',
    helper: 'Launches the test as-is. Overlapping operational changes may pollute lift measurements.',
  },
]

export const OVERLAP_TYPE_LABELS: Record<OverlapType, string> = {
  remodel: 'Remodel',
  'pricing-change': 'Pricing Change',
  'assortment-shift': 'Assortment Shift',
  'promo-test': 'Promo Test',
}

export function formatDateRange(startIso: string, endIso: string): string {
  const fmt = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }
  return `${fmt(startIso)} \u2013 ${fmt(endIso)}`
}

/** Validation gate for the Review & Concurrency step */
export function isConcurrencyReviewValid(review: ConcurrencyReviewState): boolean {
  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(review.businessOwnerEmail.trim())
  return emailOk
}

// ─────────────────────────────────────────────────────────────────────────────
// Reconciliation to Actuals & Net Lift
// ─────────────────────────────────────────────────────────────────────────────

export interface ReconciliationResult {
  baselineChainSales: number
  thisInitiativeLift: number
  otherActiveInitiativesLift: number
  realizedChainSales: number
  residualVariance: number
  residualVariancePercent: number
}

/**
 * Confirms baseline + all active initiative lifts sum back to realized chain
 * sales, surfacing any residual (unmeasured) variance cleanly rather than
 * hiding it inside a single net-lift number.
 */
export function simulateReconciliation(
  storeCount: number,
  thisInitiativeAnnualRevenue: number,
  collisions: DetectedCollisions,
): ReconciliationResult {
  const baselineChainSales = storeCount * 100_000 * 52 // rough fleet-wide baseline anchor
  const otherActiveInitiativesLift = collisions.overlappingInitiatives.reduce(
    (sum, init) => sum + init.impactedStoreCount * 1_400 * 52,
    0,
  )
  const seed = storeCount % 53
  const residualVariancePercent = Math.round((Math.abs(Math.sin(seed * 0.8)) * 1.5) * 100) / 100 // 0-1.5%
  const explainedTotal = baselineChainSales + thisInitiativeAnnualRevenue + otherActiveInitiativesLift
  const residualVariance = Math.round(explainedTotal * (residualVariancePercent / 100))
  const realizedChainSales = Math.round(explainedTotal + residualVariance)

  return {
    baselineChainSales: Math.round(baselineChainSales),
    thisInitiativeLift: Math.round(thisInitiativeAnnualRevenue),
    otherActiveInitiativesLift: Math.round(otherActiveInitiativesLift),
    realizedChainSales,
    residualVariance,
    residualVariancePercent,
  }
}
