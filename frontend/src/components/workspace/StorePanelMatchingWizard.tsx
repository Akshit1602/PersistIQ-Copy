import { useEffect, useRef, useState } from 'react'
import { Check, X, Settings, Loader2, ShieldCheck, AlertTriangle, Upload, Lock } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { InfoTooltip } from '../shared/InfoTooltip'
import {
  type StoreSourceMode,
  type CompositeMatchingAlgorithm,
  type ControlPanelResult,
  MATCHING_ALGORITHM_OPTIONS,
  EMPTY_STORE_PANEL_UPLOAD,
  simulateControlPanelGeneration,
  parseStorePanelCsv,
  isStorePanelReadyToLock,
} from '../../data/storePanelMatching'

const ALGORITHM_TRADEOFF_NOTES: Record<string, string> = {
  ai_weighted_composite: 'Best overall balance: blends DTW (curve shape) + Mahalanobis (structural covariates) + spatial risk. Slower to compute, most robust for messy real-world data.',
  dtw_only: 'Captures how closely two stores\u2019 sales curves move together over time, even if shifted slightly. Ignores structural attributes like size or demographics entirely.',
  standardized_euclidean: 'Fastest and most transparent — matches on raw structural distance (sq ft, volume, tier). Ignores sales-curve shape, so pre-trend parallelism isn\u2019t guaranteed.',
}

export function StorePanelMatchingWizard() {
  const {
    audienceWizardOpen,
    closeAudienceWizard,
    selectedExperiment,
    moduleFormValuesByExperiment,
    updateModuleFormField,
    markWorkflowStepComplete,
  } = useMatchView()

  const experimentModuleValues = moduleFormValuesByExperiment[selectedExperiment] as Record<string, any> | undefined
  const existing = experimentModuleValues?.['store-panel-matching']
  const rolloutInherited = experimentModuleValues?.['store-rollout-targeting']

  const [sourceMode, setSourceMode] = useState<StoreSourceMode>('cohort_from_validator')
  const [customUpload, setCustomUpload] = useState(EMPTY_STORE_PANEL_UPLOAD)
  const [algorithm, setAlgorithm] = useState<CompositeMatchingAlgorithm>('ai_weighted_composite')
  const [panelResult, setPanelResult] = useState<ControlPanelResult | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isLocked, setIsLocked] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [visible, setVisible] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Inherited cohort info (falls back to sensible defaults if the Rollout
  // step's data isn't available in this session yet).
  const inheritedTargetCount =
    typeof (rolloutInherited as any)?.targetStoreCount === 'number' ? (rolloutInherited as any).targetStoreCount : 500
  const inheritedAvgSize =
    typeof (rolloutInherited as any)?.avgStoreSize === 'number' ? (rolloutInherited as any).avgStoreSize : 7500
  const inheritedGoldTiers =
    typeof (rolloutInherited as any)?.goldTierSummary === 'string'
      ? (rolloutInherited as any).goldTierSummary
      : 'Tier 1: 45% · Tier 2: 40% · Tier 3: 15%'

  useEffect(() => {
    if (audienceWizardOpen) {
      setSourceMode(typeof existing?.sourceMode === 'string' ? (existing.sourceMode as StoreSourceMode) : 'cohort_from_validator')
      setAlgorithm(typeof existing?.algorithm === 'string' ? (existing.algorithm as CompositeMatchingAlgorithm) : 'ai_weighted_composite')
      setPanelResult(null)
      setIsLocked(false)
      setVisible(true)
      return
    }
    const t = window.setTimeout(() => setVisible(false), 220)
    return () => window.clearTimeout(t)
  }, [audienceWizardOpen, existing])

  useEffect(() => {
    if (!audienceWizardOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeAudienceWizard()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [audienceWizardOpen, closeAudienceWizard])

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadError(null)
    if (!/\.csv$/i.test(file.name)) {
      setUploadError('Please upload a .csv file.')
      return
    }
    const text = await file.text()
    const { storeIds, error } = parseStorePanelCsv(text)
    if (error) {
      setUploadError(error)
      setCustomUpload({ fileName: file.name, storeIds: [], error })
      return
    }
    setCustomUpload({ fileName: file.name, storeIds, error: null })
  }

  const runGenerate = async () => {
    setGenError(null)
    setIsGenerating(true)
    setPanelResult(null)
    try {
      const storeIds = sourceMode === 'custom_csv_upload' ? customUpload.storeIds : []
      const result = await simulateControlPanelGeneration(algorithm, storeIds, inheritedTargetCount)
      setPanelResult(result)
      updateModuleFormField('audience-selection' as any, 'lastResult', result)
    } catch {
      setGenError('Control panel generation failed — try again.')
    } finally {
      setIsGenerating(false)
    }
  }

  const canLock = isStorePanelReadyToLock({
    sourceMode,
    customUpload,
    algorithm,
    panelResult,
    isGenerating,
    isLocked,
  })

  const handleLock = () => {
    if (!canLock) return
    setIsLocked(true)
    markWorkflowStepComplete(selectedExperiment, 'audience-selection')
    window.setTimeout(() => closeAudienceWizard(), 600)
  }

  if (!visible && !audienceWizardOpen) return null

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <button
        type="button"
        className={`absolute inset-0 bg-black/30 transition-opacity duration-200 ${
          audienceWizardOpen ? 'opacity-100' : 'opacity-0'
        }`}
        onClick={closeAudienceWizard}
        aria-label="Close store matching wizard"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="store-panel-wizard-title"
        className={`relative flex h-full w-full max-w-[760px] flex-col border-l border-border-muted/20 bg-surface-raised shadow-glow transition-transform duration-200 ease-out ${
          audienceWizardOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-muted/20 px-4 py-3.5">
          <div>
            <h2 id="store-panel-wizard-title" className="text-sm font-semibold text-text-primary">
              Configure Store Matching & Panel Selection
            </h2>
            <p className="mt-0.5 text-xs text-text-secondary">
              Test-vs-control store pairing for {selectedExperiment || 'this experiment'}.
            </p>
          </div>
          <button
            type="button"
            onClick={closeAudienceWizard}
            className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
            aria-label="Close"
          >
            <AppIcon icon={X} size="sm" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div className="flex flex-col gap-3.5">
            {/* ─── Section 1: Target Test Store Input ─── */}
            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <p className="type-overline mb-1.5">Target Test Store Input</p>
              <div className="flex flex-col gap-2">
                <label className="flex cursor-pointer items-start gap-2 rounded-xs px-2 py-1.5 hover:bg-surface-hover">
                  <input
                    type="radio"
                    name="sourceMode"
                    className="mt-0.5 h-3.5 w-3.5 accent-current"
                    checked={sourceMode === 'cohort_from_validator'}
                    onChange={() => setSourceMode('cohort_from_validator')}
                  />
                  <span className="text-xs text-text-primary">
                    Use Cohort from Initiative Setup & Benchmarking
                  </span>
                </label>
                <label className="flex cursor-pointer items-start gap-2 rounded-xs px-2 py-1.5 hover:bg-surface-hover">
                  <input
                    type="radio"
                    name="sourceMode"
                    className="mt-0.5 h-3.5 w-3.5 accent-current"
                    checked={sourceMode === 'custom_csv_upload'}
                    onChange={() => setSourceMode('custom_csv_upload')}
                  />
                  <span className="text-xs text-text-primary">Upload Custom Pilot Location CSV (Exact Store IDs)</span>
                </label>
              </div>

              {sourceMode === 'custom_csv_upload' && (
                <div className="mt-2 rounded-xs border border-border-muted/15 bg-surface-hover/40 px-2.5 py-2.5">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={handleFileSelected}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="focus-ring flex items-center gap-1.5 rounded-xs border border-border-muted/30 bg-surface-raised px-2.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-hover"
                  >
                    <AppIcon icon={Upload} size="xs" />
                    Upload Pilot Location CSV
                  </button>
                  {customUpload.fileName && !uploadError && (
                    <p className="mt-1.5 text-micro text-text-secondary">
                      {customUpload.fileName} — {customUpload.storeIds.length.toLocaleString()} store IDs found
                    </p>
                  )}
                  {uploadError && <p className="mt-1.5 text-micro text-red-600">{uploadError}</p>}
                </div>
              )}

              {sourceMode === 'cohort_from_validator' ? (
                <div className="mt-2 grid grid-cols-3 gap-2 rounded-xs bg-surface-hover/50 px-2.5 py-2.5">
                  <div>
                    <p className="text-micro text-text-secondary">Target Store Count</p>
                    <p className="text-xs font-semibold text-text-primary tabular-nums">{inheritedTargetCount.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-micro text-text-secondary">Avg. Store Size</p>
                    <p className="text-xs font-semibold text-text-primary tabular-nums">{inheritedAvgSize.toLocaleString()} sq ft</p>
                  </div>
                  <div>
                    <p className="text-micro text-text-secondary">G.O.L.D. Tier Distribution</p>
                    <p className="text-xs font-semibold text-text-primary">{inheritedGoldTiers}</p>
                  </div>
                </div>
              ) : customUpload.storeIds.length > 0 ? (
                <div className="mt-2 rounded-xs bg-surface-hover/50 px-2.5 py-2.5">
                  <p className="text-micro text-text-secondary">Target Store Count (from uploaded CSV)</p>
                  <p className="text-xs font-semibold text-text-primary tabular-nums">{customUpload.storeIds.length.toLocaleString()}</p>
                  <p className="mt-1 text-micro text-text-secondary">
                    Store size and G.O.L.D. tier distribution aren't known until these exact store IDs are matched against the store master.
                  </p>
                </div>
              ) : null}
            </div>

            {/* ─── Section 2: Composite Matching Algorithm Selector ─── */}
            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <p className="type-overline mb-1.5">Composite Matching Algorithm</p>
              <div className="flex flex-col gap-2">
                {MATCHING_ALGORITHM_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    className="flex cursor-pointer items-start gap-2 rounded-xs px-2 py-1.5 hover:bg-surface-hover"
                  >
                    <input
                      type="radio"
                      name="algorithm"
                      className="mt-0.5 h-3.5 w-3.5 accent-current"
                      checked={algorithm === opt.value}
                      onChange={() => setAlgorithm(opt.value)}
                    />
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5">
                        <span className="block text-xs font-medium text-text-primary">{opt.label}</span>
                        <InfoTooltip text={ALGORITHM_TRADEOFF_NOTES[opt.value]} />
                      </span>
                      <span className="block text-micro text-text-secondary">{opt.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {/* ─── Section 3: Action Button & Generation State ─── */}
            <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
              <button
                type="button"
                onClick={runGenerate}
                disabled={isGenerating || (sourceMode === 'custom_csv_upload' && customUpload.storeIds.length === 0)}
                className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isGenerating ? (
                  <>
                    <AppIcon icon={Loader2} size="xs" className="animate-spin" />
                    Executing spatial trade-area buffering and computing penalized composite matches
                    across candidate donor pool…
                  </>
                ) : (
                  <>
                    <AppIcon icon={Settings} size="xs" />
                    Generate Control Store Panel
                  </>
                )}
              </button>
              {genError && <p className="mt-1.5 text-micro text-red-600">{genError}</p>}
            </div>

            {/* ─── Section 4: Output Render — Pairwise & Donor Panel Table ─── */}
            {panelResult && !isGenerating && (
              <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
                <div className="mb-2 flex items-center justify-between">
                  <p className="type-overline">Pairwise & Donor Panel</p>
                  <span className="text-micro text-text-secondary">
                    {panelResult.totalPairs.toLocaleString()} pairs · avg SMD {panelResult.averageSmd.toFixed(3)}
                    {panelResult.overlapWarningCount > 0 && (
                      <span className="ml-1.5 text-amber-700">
                        · {panelResult.overlapWarningCount} overlap warning{panelResult.overlapWarningCount > 1 ? 's' : ''}
                      </span>
                    )}
                  </span>
                </div>
                <div className="max-h-64 overflow-y-auto rounded-xs border border-border-muted/20">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-surface-hover/90">
                      <tr>
                        <th className="px-2.5 py-1.5 font-medium text-text-secondary">Test Store</th>
                        <th className="px-2.5 py-1.5 font-medium text-text-secondary">Control Match</th>
                        <th className="px-2.5 py-1.5 font-medium text-text-secondary">Confidence</th>
                        <th className="px-2.5 py-1.5 font-medium text-text-secondary">SMD</th>
                        <th className="px-2.5 py-1.5 font-medium text-text-secondary">Spatial Buffer</th>
                      </tr>
                    </thead>
                    <tbody>
                      {panelResult.pairs.slice(0, 50).map((pair) => (
                        <tr key={pair.testStoreId} className="border-t border-border-muted/15">
                          <td className="px-2.5 py-1.5 text-text-primary">{pair.testStoreLabel}</td>
                          <td className="px-2.5 py-1.5 text-text-secondary">{pair.controlStoreLabel}</td>
                          <td className="px-2.5 py-1.5 tabular-nums">
                            <span className={pair.matchConfidencePercent >= 90 ? 'text-green-700' : 'text-amber-700'}>
                              {pair.matchConfidencePercent.toFixed(1)}%{pair.matchConfidencePercent >= 90 ? ' \u2705' : ''}
                            </span>
                          </td>
                          <td className="px-2.5 py-1.5 tabular-nums text-text-primary">
                            {pair.smd.toFixed(2)} <span className="text-micro text-text-secondary">({pair.smdQuality})</span>
                          </td>
                          <td className="px-2.5 py-1.5">
                            {pair.spatialBufferStatus === 'clear' ? (
                              <span className="flex items-center gap-1 text-green-700">
                                <AppIcon icon={ShieldCheck} size="xs" /> Clear (&gt;15 mi)
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-amber-700">
                                <AppIcon icon={AlertTriangle} size="xs" /> Overlap Warning
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {panelResult.pairs.length > 50 && (
                  <p className="mt-1.5 text-micro text-text-secondary">
                    Showing 50 of {panelResult.pairs.length.toLocaleString()} matched pairs.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ─── Section 5: Final Page Action ─── */}
        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-border-muted/20 px-4 py-3">
          <button
            type="button"
            onClick={closeAudienceWizard}
            className="focus-ring rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-hover hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleLock}
            disabled={!canLock || isLocked}
            className="focus-ring inline-flex items-center gap-1 rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <AppIcon icon={isLocked ? Check : Lock} size="xs" />
            {isLocked ? 'Locked — Routing to Analytics Lab…' : 'Lock Store Panel & Proceed to Analytics Lab'}
          </button>
        </footer>
      </aside>
    </div>
  )
}
