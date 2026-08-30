/**
 * Sales Driver Decomposition: Sales Lift = Traffic × CVR × UPT × AUR
 * Used by both In-Flight Lift Trajectory (Monitoring) and ROI Synthesis
 * (Causal & ROI) — same formula, same card, two contexts.
 */

export interface DriverDecomposition {
  trafficDeltaPercent: number
  cvrDeltaPercent: number
  uptDeltaPercent: number
  aurDeltaPercent: number
  totalSalesLiftPercent: number
}

/**
 * Composes the 4 driver deltas multiplicatively (compounding, not additive) —
 * matching how Traffic × CVR × UPT × AUR actually combine in retail math.
 */
export function composeDriverDecomposition(
  trafficDeltaPercent: number,
  cvrDeltaPercent: number,
  uptDeltaPercent: number,
  aurDeltaPercent: number,
): DriverDecomposition {
  const compound =
    (1 + trafficDeltaPercent / 100) *
    (1 + cvrDeltaPercent / 100) *
    (1 + uptDeltaPercent / 100) *
    (1 + aurDeltaPercent / 100)
  const totalSalesLiftPercent = Math.round((compound - 1) * 10000) / 100

  return { trafficDeltaPercent, cvrDeltaPercent, uptDeltaPercent, aurDeltaPercent, totalSalesLiftPercent }
}

/** Deterministic simulated decomposition, seeded off store count + a context tag
 * so Monitoring (in-flight, unadjusted) and ROI Synthesis (final, causal) can
 * both use this without colliding on the same numbers. */
export function simulateDriverDecomposition(storeCount: number, contextSeed: number): DriverDecomposition {
  const seed = storeCount * 4 + contextSeed * 17
  const trafficDeltaPercent = Math.round((Math.sin(seed * 0.31) * 2.5) * 100) / 100
  const cvrDeltaPercent = Math.round((Math.abs(Math.cos(seed * 0.44)) * 3) * 100) / 100
  const uptDeltaPercent = Math.round((Math.sin(seed * 0.53) * 1.2) * 100) / 100
  const aurDeltaPercent = Math.round((Math.abs(Math.sin(seed * 0.19)) * 1.8) * 100) / 100
  return composeDriverDecomposition(trafficDeltaPercent, cvrDeltaPercent, uptDeltaPercent, aurDeltaPercent)
}
