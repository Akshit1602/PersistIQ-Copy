import { useRef, useState } from 'react'
import {
  Target,
  Radio as RadioIcon,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Info,
  Upload,
  Shuffle,
  FileCheck,
} from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import { SuggestedValueBadge } from '../shared/SuggestedValueBadge'
import type { FieldSuggestion } from '../../data/inputSuggestions'
import {
  type StoreRolloutTargeting,
  type RolloutScope,
  type DeploymentTiming,
  type ControlMethod,
  type GoldTier,
  STORE_SIZE_OPTIONS,
  DEMOGRAPHICS_OPTIONS,
  GOLD_TIER_OPTIONS,
  CONTROL_METHOD_OPTIONS,
  WAVE_COUNT_OPTIONS,
  WEEKS_BETWEEN_WAVES_OPTIONS,
  generateWaveMatrix,
  SMD_TARGET_THRESHOLD,
  simulateControlMatching,
  simulateRandomizedControl,
  simulateSyntheticControl,
  parseManualStoreCsv,
  simulateManualUploadValidation,
  EMPTY_MANUAL_UPLOAD,
} from '../../data/storeRolloutTargeting'

interface Props {
  rollout: StoreRolloutTargeting
  onChange: (partial: Partial<StoreRolloutTargeting>) => void
  /** Field-keyed suggestions from the store dimension behind this project. */
  suggestions?: Record<string, FieldSuggestion>
}

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
const selectClass = `${inputClass} appearance-none bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat pr-8`
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"

function SectionHeader({ title, helper }: { title: string; helper?: string }) {
  return (
    <div>
      <p className="type-overline">{title}</p>
      {helper && <p className="mt-0.5 text-micro text-text-secondary leading-relaxed">{helper}</p>}
    </div>
  )
}

export function StoreRolloutTargetingStep({ rollout, onChange, suggestions = {} }: Props) {
  const [matchError, setMatchError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const isPartial = rollout.rolloutScope === 'partial_rollout'
  const isStaggered = rollout.deploymentSchedule.timing === 'staggered_waves'
  const isAiMatching = rollout.controlMethod === 'ai_twin_matching'
  const isPureRandomized = rollout.controlMethod === 'pure_randomized'
  const isManualUpload = rollout.controlMethod === 'manual_upload'
  const isPenalizedSynthetic = rollout.controlMethod === 'penalized_synthetic_control'

  const patchFilters = (partial: Partial<StoreRolloutTargeting['treatmentFilters']>) =>
    onChange({ treatmentFilters: { ...rollout.treatmentFilters, ...partial } })

  const patchSchedule = (partial: Partial<StoreRolloutTargeting['deploymentSchedule']>) =>
    onChange({ deploymentSchedule: { ...rollout.deploymentSchedule, ...partial } })

  const toggleGoldTier = (tier: GoldTier) => {
    const current = rollout.treatmentFilters.goldTiers
    const next = current.includes(tier) ? current.filter((t) => t !== tier) : [...current, tier]
    patchFilters({ goldTiers: next })
  }

  const runAutoMatch = async () => {
    setMatchError(null)
    onChange({ isMatching: true, matchResult: null })
    try {
      const result = await simulateControlMatching(rollout.treatmentFilters)
      onChange({ isMatching: false, matchResult: result })
    } catch {
      setMatchError('Matching failed — try again.')
      onChange({ isMatching: false })
    }
  }

  const runRandomize = async () => {
    setMatchError(null)
    onChange({ isMatching: true, matchResult: null })
    try {
      const result = await simulateRandomizedControl(rollout.treatmentFilters)
      onChange({ isMatching: false, matchResult: result })
    } catch {
      setMatchError('Randomization failed — try again.')
      onChange({ isMatching: false })
    }
  }

  const runSyntheticControl = async () => {
    setMatchError(null)
    onChange({ isMatching: true, matchResult: null })
    try {
      const result = await simulateSyntheticControl(rollout.treatmentFilters)
      onChange({ isMatching: false, matchResult: result })
    } catch {
      setMatchError('Synthetic control build failed — try again.')
      onChange({ isMatching: false })
    }
  }

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadError(null)
    onChange({ matchResult: null })

    if (!/\.csv$/i.test(file.name)) {
      setUploadError('Please upload a .csv file.')
      return
    }

    const text = await file.text()
    const { storeIds, error } = parseManualStoreCsv(text)
    if (error) {
      setUploadError(error)
      onChange({ manualUpload: { fileName: file.name, storeIds: [], error } })
      return
    }

    onChange({
      manualUpload: { fileName: file.name, storeIds, error: null },
      isMatching: true,
    })
    const result = await simulateManualUploadValidation(storeIds, rollout.treatmentFilters)
    onChange({ isMatching: false, matchResult: result })
  }

  const clearManualUpload = () => {
    setUploadError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
    onChange({ manualUpload: EMPTY_MANUAL_UPLOAD, matchResult: null })
  }

  const smd = rollout.matchResult?.smd ?? null
  const smdOk = smd !== null && smd < SMD_TARGET_THRESHOLD

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <p className="text-sm font-semibold text-text-primary">Rollout & Store Targeting</p>
        <p className="mt-0.5 text-xs text-text-secondary">
          Define which stores receive this initiative and how the system finds a credible control group.
        </p>
      </div>

      {/* ─── Section 1: Rollout Scope (master toggle) ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <SectionHeader title="Rollout Strategy" />
        <div className="mt-2 flex flex-col gap-2">
          {(
            [
              { value: 'partial_rollout' as RolloutScope, label: 'Partial Rollout (Targeted Stores)' },
              { value: 'fleet_wide_rollout' as RolloutScope, label: '100% Fleet-Wide Rollout (Across all stores)' },
            ]
          ).map((opt) => (
            <label
              key={opt.value}
              className="flex cursor-pointer items-center gap-2 rounded-xs px-2 py-1.5 hover:bg-surface-hover"
            >
              <input
                type="radio"
                name="rolloutScope"
                className="h-3.5 w-3.5 accent-current text-border-muted"
                checked={rollout.rolloutScope === opt.value}
                onChange={() => onChange({ rolloutScope: opt.value })}
              />
              <span className="text-xs text-text-primary">{opt.label}</span>
            </label>
          ))}
        </div>
        {!isPartial && (
          <p className="mt-2 rounded-xs border border-border-muted/20 bg-surface-hover/60 px-2.5 py-2 text-micro text-text-secondary leading-relaxed">
            100% rollout means there's no held-back control pool within the fleet — Analysis will recommend
            an interrupted time-series or pre/post design instead of a matched control comparison.
          </p>
        )}
      </div>

      {isPartial && (
        <>
          {/* ─── Section 2: Treatment Group Filters ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <SectionHeader title="Target Store Characteristics" />
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Target Store Count</label>
                <input
                  type="number"
                  className={inputClass}
                  value={rollout.treatmentFilters.targetStoreCount}
                  min={1}
                  max={100000}
                  step={50}
                  placeholder="e.g. 500"
                  onChange={(e) => patchFilters({ targetStoreCount: Number(e.target.value) || 0 })}
                />
                {suggestions.targetStoreCount ? (
                  <SuggestedValueBadge
                    suggestion={suggestions.targetStoreCount}
                    value={rollout.treatmentFilters.targetStoreCount}
                    formatValue={(v) => `${Number(v).toLocaleString()} stores`}
                    onApply={(v) => patchFilters({ targetStoreCount: Number(v) || 0 })}
                  />
                ) : null}
              </div>
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Store Size (Sq Ft)</label>
                <select
                  className={selectClass}
                  style={{ backgroundImage: selectChevronBg }}
                  value={rollout.treatmentFilters.storeSize}
                  onChange={(e) => patchFilters({ storeSize: e.target.value as typeof rollout.treatmentFilters.storeSize })}
                >
                  {STORE_SIZE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Demographics</label>
                <select
                  className={selectClass}
                  style={{ backgroundImage: selectChevronBg }}
                  value={rollout.treatmentFilters.demographics}
                  onChange={(e) => patchFilters({ demographics: e.target.value as typeof rollout.treatmentFilters.demographics })}
                >
                  {DEMOGRAPHICS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">G.O.L.D. Score Tier</label>
                <div className="flex flex-col gap-1 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5">
                  {GOLD_TIER_OPTIONS.map((tier) => (
                    <label key={tier.value} className="flex cursor-pointer items-center gap-1.5">
                      <input
                        type="checkbox"
                        className="h-3 w-3 accent-current"
                        checked={rollout.treatmentFilters.goldTiers.includes(tier.value)}
                        onChange={() => toggleGoldTier(tier.value)}
                      />
                      <span className="text-xs text-text-primary">{tier.label}</span>
                      <span className="text-micro text-text-secondary">— {tier.hint}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Household Income Decile</label>
                <select
                  className={selectClass}
                  style={{ backgroundImage: selectChevronBg }}
                  value={rollout.treatmentFilters.incomeDecile}
                  onChange={(e) => patchFilters({ incomeDecile: Number(e.target.value) as typeof rollout.treatmentFilters.incomeDecile })}
                >
                  {Array.from({ length: 10 }, (_, i) => i + 1).map((d) => (
                    <option key={d} value={d}>Decile {d}{d === 1 ? ' (Lowest income)' : d === 10 ? ' (Highest income)' : ''}</option>
                  ))}
                </select>
              </div>
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Register Count</label>
                <input
                  type="number"
                  className={inputClass}
                  value={rollout.treatmentFilters.registerCount}
                  min={1}
                  max={40}
                  placeholder="e.g. 4"
                  onChange={(e) => patchFilters({ registerCount: Number(e.target.value) || 1 })}
                />
              </div>
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Baseline Volume Decile</label>
                <select
                  className={selectClass}
                  style={{ backgroundImage: selectChevronBg }}
                  value={rollout.treatmentFilters.volumeDecile}
                  onChange={(e) => patchFilters({ volumeDecile: Number(e.target.value) as typeof rollout.treatmentFilters.volumeDecile })}
                >
                  {Array.from({ length: 10 }, (_, i) => i + 1).map((d) => (
                    <option key={d} value={d}>Decile {d}{d === 1 ? ' (Lowest volume)' : d === 10 ? ' (Highest volume)' : ''}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* ─── Spatial Buffer + Stratification & Triage ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <SectionHeader
              title="Spatial Buffer & Store Triage"
              helper="Excludes candidate control stores that share a trade area with a treated store, and prunes stores not yet eligible."
            />
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Drive-Time Exclusion Radius (miles)</label>
                <input
                  type="number"
                  className={inputClass}
                  value={rollout.spatialFilters.driveTimeExclusionMiles}
                  min={1}
                  max={50}
                  onChange={(e) =>
                    onChange({
                      spatialFilters: { ...rollout.spatialFilters, driveTimeExclusionMiles: Number(e.target.value) || 0 },
                    })
                  }
                />
                <p className="mt-0.5 text-micro text-text-secondary">
                  Control stores within this radius of any treated store are excluded — prevents shared
                  trade-area contamination.
                </p>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-current"
                    checked={rollout.spatialFilters.excludeNewStores}
                    onChange={(e) =>
                      onChange({ spatialFilters: { ...rollout.spatialFilters, excludeNewStores: e.target.checked } })
                    }
                  />
                  <span className="text-xs text-text-primary">Exclude stores open &lt; 12 months</span>
                </label>
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-current"
                    checked={rollout.spatialFilters.excludeScheduledRemodels}
                    onChange={(e) =>
                      onChange({ spatialFilters: { ...rollout.spatialFilters, excludeScheduledRemodels: e.target.checked } })
                    }
                  />
                  <span className="text-xs text-text-primary">Exclude stores scheduled for remodel</span>
                </label>
              </div>
            </div>
          </div>

          {/* ─── Section 3: Deployment Timing ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <SectionHeader title="Deployment Schedule" />
            <div className="mt-2 flex flex-col gap-2">
              {(
                [
                  { value: 'single_wave' as DeploymentTiming, label: 'Single Wave (Concurrent Blast)', hint: 'Deploys to all target stores on the same date.' },
                  { value: 'staggered_waves' as DeploymentTiming, label: 'Staggered Waves (Phased Deployment)', hint: 'Splits storefronts into chronological waves.' },
                ]
              ).map((opt) => (
                <label
                  key={opt.value}
                  className="flex cursor-pointer items-start gap-2 rounded-xs px-2 py-1.5 hover:bg-surface-hover"
                >
                  <input
                    type="radio"
                    name="deploymentTiming"
                    className="mt-0.5 h-3.5 w-3.5 accent-current"
                    checked={rollout.deploymentSchedule.timing === opt.value}
                    onChange={() => patchSchedule({ timing: opt.value })}
                  />
                  <span className="min-w-0">
                    <span className="block text-xs text-text-primary">{opt.label}</span>
                    <span className="block text-micro text-text-secondary">{opt.hint}</span>
                  </span>
                </label>
              ))}
            </div>

            {isStaggered && (
              <div className="mt-2 grid grid-cols-2 gap-3 rounded-xs border border-border-muted/15 bg-surface-hover/40 px-2.5 py-2.5">
                <div className="min-w-0">
                  <label className="type-caption mb-0.5 block">Number of Waves</label>
                  <select
                    className={selectClass}
                    style={{ backgroundImage: selectChevronBg }}
                    value={rollout.deploymentSchedule.numberOfWaves}
                    onChange={(e) => patchSchedule({ numberOfWaves: Number(e.target.value) })}
                  >
                    {WAVE_COUNT_OPTIONS.map((n) => (
                      <option key={n} value={n}>{n} waves</option>
                    ))}
                  </select>
                </div>
                <div className="min-w-0">
                  <label className="type-caption mb-0.5 block">Weeks Between Waves</label>
                  <select
                    className={selectClass}
                    style={{ backgroundImage: selectChevronBg }}
                    value={rollout.deploymentSchedule.weeksBetweenWaves}
                    onChange={(e) => patchSchedule({ weeksBetweenWaves: Number(e.target.value) })}
                  >
                    {WEEKS_BETWEEN_WAVES_OPTIONS.map((n) => (
                      <option key={n} value={n}>{n} week{n > 1 ? 's' : ''}</option>
                    ))}
                  </select>
                </div>

                <div className="col-span-2">
                  <div className="mb-1 flex items-center justify-between">
                    <label className="type-caption block">Phased Rollout Matrix</label>
                    <button
                      type="button"
                      onClick={() =>
                        patchSchedule({
                          waves: generateWaveMatrix(
                            rollout.deploymentSchedule.numberOfWaves,
                            rollout.deploymentSchedule.weeksBetweenWaves,
                            rollout.treatmentFilters.targetStoreCount,
                          ),
                        })
                      }
                      className="focus-ring text-micro text-border-muted underline hover:text-text-primary"
                    >
                      Regenerate evenly
                    </button>
                  </div>
                  <div className="overflow-hidden rounded-xs border border-border-muted/20">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="bg-surface-hover/60">
                          <th className="px-2 py-1 font-medium text-text-secondary">Wave</th>
                          <th className="px-2 py-1 font-medium text-text-secondary">Store Count</th>
                          <th className="px-2 py-1 font-medium text-text-secondary">Launch Fiscal Week</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rollout.deploymentSchedule.waves.map((wave, idx) => (
                          <tr key={wave.waveId} className="border-t border-border-muted/10">
                            <td className="px-2 py-1 text-text-primary">Wave {wave.waveId}</td>
                            <td className="px-2 py-1">
                              <input
                                type="number"
                                className="w-24 rounded-xs border border-border-muted/25 bg-surface-base px-1.5 py-0.5 text-xs"
                                value={wave.storeCount}
                                min={0}
                                onChange={(e) => {
                                  const waves = [...rollout.deploymentSchedule.waves]
                                  waves[idx] = { ...wave, storeCount: Number(e.target.value) || 0 }
                                  patchSchedule({ waves })
                                }}
                              />
                            </td>
                            <td className="px-2 py-1">
                              <input
                                type="number"
                                className="w-20 rounded-xs border border-border-muted/25 bg-surface-base px-1.5 py-0.5 text-xs"
                                value={wave.launchFiscalWeek}
                                min={1}
                                onChange={(e) => {
                                  const waves = [...rollout.deploymentSchedule.waves]
                                  waves[idx] = { ...wave, launchFiscalWeek: Number(e.target.value) || 1 }
                                  patchSchedule({ waves })
                                }}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-1.5 text-micro text-text-secondary">
                    Total across waves: {rollout.deploymentSchedule.waves.reduce((s, w) => s + w.storeCount, 0).toLocaleString()} stores
                    (target: {rollout.treatmentFilters.targetStoreCount.toLocaleString()})
                  </p>
                  <p className="mt-1.5 flex items-center gap-1.5 rounded-xs bg-blue-50/40 px-2 py-1.5 text-micro text-blue-700">
                    Recommended downstream estimator: <strong>Staggered DiD (Callaway &amp; Sant'Anna)</strong> — this
                    will be pre-selected in the Causal Inference Engine.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* ─── Control Group Methodology ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <SectionHeader title="Control Store Selection Method" helper="Choose how the system identifies control stores for this experiment." />
            <div className="mt-2 flex flex-col gap-2">
              {CONTROL_METHOD_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className="flex cursor-pointer items-start gap-2 rounded-xs px-2 py-1.5 hover:bg-surface-hover"
                >
                  <input
                    type="radio"
                    name="controlMethod"
                    className="mt-0.5 h-3.5 w-3.5 accent-current"
                    checked={rollout.controlMethod === opt.value}
                    onChange={() => onChange({ controlMethod: opt.value as ControlMethod, matchResult: null })}
                  />
                  <span className="min-w-0">
                    <span className="block text-xs font-medium text-text-primary">{opt.label}</span>
                    <span className="block text-micro text-text-secondary">{opt.description}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* ─── Section 4: Intelligent Control Selection (AI Action) ─── */}
          {isAiMatching && (
            <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
              <div className="flex items-center gap-2">
                <AppIcon icon={Sparkles} size="sm" className="text-border-muted" />
                <p className="text-sm font-semibold text-text-primary">AI Control Matching</p>
              </div>
              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                Instead of manually selecting control stores, our engine uses Dynamic Time Warping to
                automatically scan the remaining fleet and find identical store twins based on historical
                sales curves.
              </p>
              <button
                type="button"
                onClick={runAutoMatch}
                disabled={rollout.isMatching}
                className="focus-ring mt-3 flex items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {rollout.isMatching ? (
                  <>
                    <AppIcon icon={Loader2} size="xs" className="animate-spin" />
                    Calculating matches…
                  </>
                ) : (
                  <>
                    <AppIcon icon={Target} size="xs" />
                    Auto-Match Control Stores
                  </>
                )}
              </button>
              {matchError && <p className="mt-1.5 text-micro text-red-600">{matchError}</p>}
            </div>
          )}

          {/* ─── Pure Randomized Control action ─── */}
          {isPureRandomized && (
            <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
              <div className="flex items-center gap-2">
                <AppIcon icon={Shuffle} size="sm" className="text-border-muted" />
                <p className="text-sm font-semibold text-text-primary">Randomized Control Draw</p>
              </div>
              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                Randomly selects stores from the same G.O.L.D. tier(s) as the treatment group — no
                curve-shape matching, just stratified random assignment.
              </p>
              <button
                type="button"
                onClick={runRandomize}
                disabled={rollout.isMatching}
                className="focus-ring mt-3 flex items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {rollout.isMatching ? (
                  <>
                    <AppIcon icon={Loader2} size="xs" className="animate-spin" />
                    Drawing sample…
                  </>
                ) : (
                  <>
                    <AppIcon icon={Shuffle} size="xs" />
                    Randomize Now
                  </>
                )}
              </button>
              {matchError && <p className="mt-1.5 text-micro text-red-600">{matchError}</p>}
            </div>
          )}

          {/* ─── Manual Store Upload action ─── */}
          {isManualUpload && (
            <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
              <div className="flex items-center gap-2">
                <AppIcon icon={Upload} size="sm" className="text-border-muted" />
                <p className="text-sm font-semibold text-text-primary">Manual Store Upload</p>
              </div>
              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                Upload a CSV of exact store IDs to use as controls — one store ID per line (an optional
                "store_id" header row is fine).
              </p>

              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={handleFileSelected}
              />

              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={rollout.isMatching}
                  className="focus-ring flex items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {rollout.isMatching ? (
                    <>
                      <AppIcon icon={Loader2} size="xs" className="animate-spin" />
                      Validating upload…
                    </>
                  ) : (
                    <>
                      <AppIcon icon={Upload} size="xs" />
                      Upload Control Store CSV
                    </>
                  )}
                </button>
                {rollout.manualUpload.fileName && !rollout.isMatching && (
                  <button
                    type="button"
                    onClick={clearManualUpload}
                    className="focus-ring text-micro text-text-secondary underline hover:text-text-primary"
                  >
                    Clear
                  </button>
                )}
              </div>

              {rollout.manualUpload.fileName && !uploadError && (
                <p className="mt-2 flex items-center gap-1.5 text-micro text-text-secondary">
                  <AppIcon icon={FileCheck} size="xs" className="text-green-600" />
                  {rollout.manualUpload.fileName} — {rollout.manualUpload.storeIds.length.toLocaleString()} store IDs found
                </p>
              )}
              {uploadError && <p className="mt-1.5 text-micro text-red-600">{uploadError}</p>}
            </div>
          )}

          {/* ─── Penalized Synthetic Control action ─── */}
          {isPenalizedSynthetic && (
            <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
              <div className="flex items-center gap-2">
                <AppIcon icon={Sparkles} size="sm" className="text-border-muted" />
                <p className="text-sm font-semibold text-text-primary">Penalized Synthetic Control</p>
              </div>
              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                Builds a weighted composite donor pool per treated store, with a penalty that discourages
                extreme-weight interpolation — a flagship and a rural store will never be blended to fake
                a mid-tier twin.
              </p>
              <button
                type="button"
                onClick={runSyntheticControl}
                disabled={rollout.isMatching}
                className="focus-ring mt-3 flex items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {rollout.isMatching ? (
                  <>
                    <AppIcon icon={Loader2} size="xs" className="animate-spin" />
                    Building synthetic control…
                  </>
                ) : (
                  <>
                    <AppIcon icon={Target} size="xs" />
                    Build Penalized Synthetic Control
                  </>
                )}
              </button>
              {matchError && <p className="mt-1.5 text-micro text-red-600">{matchError}</p>}
            </div>
          )}

          {/* ─── Section 5: Match Validation ─── */}
          {rollout.matchResult && !rollout.isMatching && (
            <div
              className={`rounded-[8px] border px-4 py-4 ${
                smdOk ? 'border-green-500/30 bg-green-50/5' : 'border-red-500/30 bg-red-50/5'
              }`}
            >
              <div className="flex items-center gap-2 mb-3">
                <AppIcon icon={RadioIcon} size="sm" />
                <p className="text-sm font-semibold text-text-primary">Validation Results</p>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="rounded-xs bg-surface-raised/60 px-3 py-2.5">
                  <p className="text-micro text-text-secondary">Treatment Group Size</p>
                  <p className="text-sm font-semibold text-text-primary tabular-nums">
                    {rollout.matchResult.treatmentGroupSize.toLocaleString()} stores
                  </p>
                </div>
                <div className="rounded-xs bg-surface-raised/60 px-3 py-2.5">
                  <p className="text-micro text-text-secondary">Control Group Size</p>
                  <p className="text-sm font-semibold text-text-primary tabular-nums">
                    {rollout.matchResult.controlGroupSize.toLocaleString()} stores
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-between rounded-xs bg-surface-raised/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-secondary">Match Quality (SMD)</span>
                  <span className="group relative inline-flex">
                    <button
                      type="button"
                      className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-text-secondary hover:text-border-muted"
                      aria-label="Standardized Mean Difference — target under 0.10"
                    >
                      <AppIcon icon={Info} size="xs" />
                    </button>
                    <span
                      role="tooltip"
                      className="pointer-events-none absolute left-0 top-full z-30 mt-1 w-[190px] rounded-xs border border-border-muted/20 bg-text-primary px-2 py-1.5 text-micro text-white opacity-0 shadow-md group-hover:opacity-100"
                    >
                      Standardized Mean Difference across matched covariates. Below 0.10 indicates the
                      treatment and control groups are statistically comparable.
                    </span>
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-bold tabular-nums ${smdOk ? 'text-green-600' : 'text-red-600'}`}>
                    {rollout.matchResult.smd.toFixed(3)}
                  </span>
                  <span
                    className={`flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-micro font-medium ${
                      smdOk ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                    }`}
                  >
                    <AppIcon icon={smdOk ? CheckCircle2 : AlertTriangle} size="xs" />
                    {smdOk ? 'Target met' : 'Above target'}
                  </span>
                </div>
              </div>

              {rollout.matchResult.compositeDistance !== undefined && (
                <div className="mt-3 rounded-xs bg-surface-raised/60 px-3 py-2.5">
                  <p className="mb-1.5 text-xs text-text-secondary">
                    Composite Distance Score (D<sub>composite</sub>) = 0.50 × DTW + 0.35 × Mahalanobis + 0.15 × Spillover Risk
                  </p>
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div>
                      <p className="text-micro text-text-secondary">DTW</p>
                      <p className="text-xs font-semibold text-text-primary tabular-nums">{rollout.matchResult.dtwComponent?.toFixed(3)}</p>
                    </div>
                    <div>
                      <p className="text-micro text-text-secondary">Mahalanobis</p>
                      <p className="text-xs font-semibold text-text-primary tabular-nums">{rollout.matchResult.mahalanobisComponent?.toFixed(3)}</p>
                    </div>
                    <div>
                      <p className="text-micro text-text-secondary">Spillover Risk</p>
                      <p className="text-xs font-semibold text-text-primary tabular-nums">{rollout.matchResult.spilloverRisk?.toFixed(3)}</p>
                    </div>
                    <div>
                      <p className="text-micro text-text-secondary">D<sub>composite</sub></p>
                      <p className="text-xs font-bold text-border-muted tabular-nums">{rollout.matchResult.compositeDistance?.toFixed(3)}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
