/**
 * Store Channel — Store Matching & Panel Selection Module
 *
 * Replaces the digital Audience Selection wizard for store-channel
 * experiments. Runs after the Initiative Setup & Benchmarking brief is generated:
 *   Section 1: Target Test Store Input (inherited cohort, or custom upload)
 *   Section 2: Composite Matching Algorithm Selector
 *   Section 3: Generate Control Store Panel (action)
 *   Section 4: Pairwise & Donor Panel Table (output)
 *   Section 5: Lock Store Panel & Proceed to Analytics Lab
 */

export type StoreSourceMode = 'cohort_from_validator' | 'custom_csv_upload'

export type CompositeMatchingAlgorithm = 'ai_weighted_composite' | 'dtw_only' | 'standardized_euclidean'

export const MATCHING_ALGORITHM_OPTIONS: {
  value: CompositeMatchingAlgorithm
  label: string
  description: string
}[] = [
  {
    value: 'ai_weighted_composite',
    label: 'AI-Weighted Composite Score (Recommended)',
    description:
      'Combines Dynamic Time Warping (DTW) for sales trajectory, Mahalanobis distance for physical attributes, and spatial buffer masking.',
  },
  {
    value: 'dtw_only',
    label: 'Dynamic Time Warping (DTW)',
    description: 'Strictly aligns 52-week historical sales curves.',
  },
  {
    value: 'standardized_euclidean',
    label: 'Standardized Euclidean Distance',
    description: 'Strictly matches on structural retail variables (sq ft, volume decile, G.O.L.D. tier).',
  },
]

export interface StorePanelManualUpload {
  fileName: string | null
  storeIds: string[]
  error: string | null
}

export const EMPTY_STORE_PANEL_UPLOAD: StorePanelManualUpload = {
  fileName: null,
  storeIds: [],
  error: null,
}

export type SmdQuality = 'Excellent' | 'Good' | 'Marginal' | 'Poor'
export type SpatialBufferStatus = 'clear' | 'overlap_warning'

export interface StorePair {
  testStoreId: string
  testStoreLabel: string
  controlStoreId: string
  controlStoreLabel: string
  matchConfidencePercent: number
  smd: number
  smdQuality: SmdQuality
  spatialBufferStatus: SpatialBufferStatus
}

export interface ControlPanelResult {
  pairs: StorePair[]
  totalPairs: number
  averageSmd: number
  overlapWarningCount: number
  algorithm: CompositeMatchingAlgorithm
  generatedAtIso: string
}

export interface StorePanelMatchingState {
  sourceMode: StoreSourceMode
  customUpload: StorePanelManualUpload
  algorithm: CompositeMatchingAlgorithm
  panelResult: ControlPanelResult | null
  isGenerating: boolean
  isLocked: boolean
}

export const STORE_PANEL_MATCHING_DEFAULTS: StorePanelMatchingState = {
  sourceMode: 'cohort_from_validator',
  customUpload: EMPTY_STORE_PANEL_UPLOAD,
  algorithm: 'ai_weighted_composite',
  panelResult: null,
  isGenerating: false,
  isLocked: false,
}

const REGION_LABELS = ['Urban', 'Suburban', 'Rural']
const DEMO_FORMAT_LABELS = ['Large-Format', 'Standard', 'Compact']

function smdQualityFor(smd: number): SmdQuality {
  if (smd < 0.05) return 'Excellent'
  if (smd < 0.1) return 'Good'
  if (smd < 0.15) return 'Marginal'
  return 'Poor'
}

/**
 * Generates the pairwise test/control matches for the target cohort. A real
 * deployment would call the backend, which runs the selected algorithm
 * against dev.matchview_store.store_master / store_performance_weekly.
 * Deterministic given the same inputs.
 */
export function simulateControlPanelGeneration(
  algorithm: CompositeMatchingAlgorithm,
  storeIds: string[],
  targetStoreCount: number,
): Promise<ControlPanelResult> {
  return new Promise((resolve) => {
    const n = storeIds.length > 0 ? storeIds.length : Math.min(targetStoreCount, 500)
    const delayMs = 1400 + (n % 600)

    // Each algorithm has a characteristic SMD distribution: the composite
    // score is tightest, DTW-only slightly wider, Euclidean widest (since it
    // ignores sales-curve shape entirely).
    const baseByAlgorithm: Record<CompositeMatchingAlgorithm, number> = {
      ai_weighted_composite: 0.02,
      dtw_only: 0.035,
      standardized_euclidean: 0.05,
    }
    const spreadByAlgorithm: Record<CompositeMatchingAlgorithm, number> = {
      ai_weighted_composite: 0.08,
      dtw_only: 0.11,
      standardized_euclidean: 0.16,
    }

    const pairs: StorePair[] = []
    let overlapWarningCount = 0
    let smdSum = 0

    for (let i = 0; i < n; i++) {
      const testId = storeIds[i] ?? `S${(1000 + i).toString().padStart(5, '0')}`
      const controlIdNum = 9000 + i
      const seed = (i + 1) * 37 + testId.length * 11
      const pseudoRandom = Math.abs(Math.sin(seed * 0.51))
      const smd = Math.round((baseByAlgorithm[algorithm] + pseudoRandom * spreadByAlgorithm[algorithm]) * 1000) / 1000
      const matchConfidencePercent = Math.round((99 - smd * 130) * 10) / 10
      const region = REGION_LABELS[i % REGION_LABELS.length]
      const format = DEMO_FORMAT_LABELS[i % DEMO_FORMAT_LABELS.length]
      const spilloverA = Math.abs(Math.cos(seed * 0.83))
      const spilloverB = Math.abs(Math.sin(seed * 1.31 + 2.7))
      const spatialBufferStatus: SpatialBufferStatus = spilloverA * spilloverB > 0.85 ? 'overlap_warning' : 'clear'
      if (spatialBufferStatus === 'overlap_warning') overlapWarningCount++
      smdSum += smd

      pairs.push({
        testStoreId: testId,
        testStoreLabel: `Store #${testId.replace(/\D/g, '').slice(-4) || (1000 + i)} (${region})`,
        controlStoreId: `S${controlIdNum}`,
        controlStoreLabel: `Store #${controlIdNum} (Control, ${format})`,
        matchConfidencePercent,
        smd,
        smdQuality: smdQualityFor(smd),
        spatialBufferStatus,
      })
    }

    window.setTimeout(() => {
      resolve({
        pairs,
        totalPairs: pairs.length,
        averageSmd: Math.round((smdSum / Math.max(pairs.length, 1)) * 1000) / 1000,
        overlapWarningCount,
        algorithm,
        generatedAtIso: new Date().toISOString(),
      })
    }, delayMs)
  })
}

export function parseStorePanelCsv(csvText: string): { storeIds: string[]; error: string | null } {
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

export function isStorePanelReadyToLock(state: StorePanelMatchingState): boolean {
  return state.panelResult !== null && state.panelResult.pairs.length > 0
}
