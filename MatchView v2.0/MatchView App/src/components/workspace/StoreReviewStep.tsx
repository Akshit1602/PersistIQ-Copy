import { useEffect, useState } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  CheckCircle2,
  X,
} from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import {
  type ConcurrencyReviewState,
  type CollisionHandlingStrategy,
  COLLISION_STRATEGY_OPTIONS,
  OVERLAP_TYPE_LABELS,
  formatDateRange,
  detectCollisions,
  isConcurrencyReviewValid,
  simulateReconciliation,
} from '../../data/storeConcurrencyReview'
import type { StoreRolloutTargeting } from '../../data/storeRolloutTargeting'
import type { StorePowerConfig } from '../../data/storePowerGuardrails'
import { computeMde, isAdequatelyPowered } from '../../data/storePowerGuardrails'
import { formatCurrency } from '../../data/storeHypothesisValidator'
import { STORE_SIZE_OPTIONS, DEMOGRAPHICS_OPTIONS, GOLD_TIER_OPTIONS } from '../../data/storeRolloutTargeting'

interface Props {
  review: ConcurrencyReviewState
  onChange: (partial: Partial<ConcurrencyReviewState>) => void
  hypothesisName: string
  primaryKpiLabel: string
  projectedNetRoi: number
  rollout: StoreRolloutTargeting
  power: StorePowerConfig
  targetLiftPercent: number
  onDeploy: () => void
  isDeploying: boolean
}

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'

function cohortScopeLabel(rollout: StoreRolloutTargeting): string {
  if (rollout.rolloutScope === 'fleet_wide_rollout') return '100% Fleet-Wide (All Stores)'
  const { targetStoreCount, storeSize, demographics, goldTiers } = rollout.treatmentFilters
  const sizeLabel = STORE_SIZE_OPTIONS.find((o) => o.value === storeSize)?.label ?? storeSize
  const demoLabel = DEMOGRAPHICS_OPTIONS.find((o) => o.value === demographics)?.label ?? demographics
  const tierLabel = goldTiers
    .map((t) => GOLD_TIER_OPTIONS.find((o) => o.value === t)?.label.replace('Tier ', '') ?? t)
    .join('/')
  return `${targetStoreCount.toLocaleString()} Stores (${demoLabel}, ${sizeLabel}${tierLabel ? `, Tier ${tierLabel}` : ''})`
}

function controlMethodLabel(rollout: StoreRolloutTargeting): string {
  const methodLabels: Record<string, string> = {
    ai_twin_matching: 'AI-Assisted Twin Matching',
    pure_randomized: 'Pure Randomized Control',
    manual_upload: 'Manual Store Upload',
  }
  const base = methodLabels[rollout.controlMethod] ?? rollout.controlMethod
  if (rollout.matchResult) {
    const smdOk = rollout.matchResult.smd < 0.1
    return `${base} (SMD: ${rollout.matchResult.smd.toFixed(2)} ${smdOk ? '\u2705' : '\u26A0\uFE0F'})`
  }
  return `${base} (not yet run)`
}

function deploymentScheduleLabel(rollout: StoreRolloutTargeting): string {
  if (rollout.deploymentSchedule.timing === 'single_wave') return 'Single Wave (Concurrent Blast)'
  return `Staggered Waves (${rollout.deploymentSchedule.numberOfWaves} waves, ${rollout.deploymentSchedule.weeksBetweenWaves}wk apart)`
}

export function StoreReviewStep({
  review,
  onChange,
  hypothesisName,
  primaryKpiLabel,
  projectedNetRoi,
  rollout,
  power,
  targetLiftPercent,
  onDeploy,
  isDeploying,
}: Props) {
  const [showConfirm, setShowConfirm] = useState(false)

  const storeCount = rollout.matchResult?.treatmentGroupSize ?? rollout.treatmentFilters.targetStoreCount

  // Run the collision scan once when Review is reached (or if the target
  // cohort size changes) — mimics a real-time backend audit.
  useEffect(() => {
    if (rollout.rolloutScope === 'partial_rollout' && storeCount > 0) {
      onChange({ detectedCollisions: detectCollisions(storeCount) })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeCount, rollout.rolloutScope])

  const collisions = review.detectedCollisions
  const hasCollisions = collisions.collidingStoresCount > 0
  const mdePercent = computeMde(power, storeCount) * 100
  const adequatelyPowered = isAdequatelyPowered(targetLiftPercent, mdePercent)
  const formValid = isConcurrencyReviewValid(review)
  const reconciliation = simulateReconciliation(storeCount, projectedNetRoi, collisions)

  const handleDeployClick = () => {
    if (!formValid || isDeploying) return
    setShowConfirm(true)
  }

  const [emailStatus, setEmailStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [emailError, setEmailError] = useState<string | null>(null)

  const confirmDeploy = async () => {
    setShowConfirm(false)
    onChange({ isReadyForLaunch: true })
    onDeploy()

    setEmailStatus('sending')
    setEmailError(null)
    try {
      const summaryHtml = `
        <ul>
          <li>Target cohort: ${cohortScopeLabel(rollout)}</li>
          <li>Control method: ${controlMethodLabel(rollout)}</li>
          <li>Deployment schedule: ${deploymentScheduleLabel(rollout)}</li>
          <li>Statistical viability: ${adequatelyPowered ? 'ADEQUATELY POWERED' : 'UNDERPOWERED'} (Target Lift ${targetLiftPercent.toFixed(1)}%, MDE ${mdePercent.toFixed(1)}%)</li>
        </ul>
      `
      const res = await fetch('/api/send-deploy-notification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          toEmail: review.businessOwnerEmail,
          experimentName: hypothesisName || 'Untitled Experiment',
          summaryHtml,
          notes: review.experimentNotes,
        }),
      })
      const json = await res.json()
      if (json.sent) {
        setEmailStatus('sent')
      } else {
        setEmailStatus('error')
        setEmailError(json.error || 'Email could not be sent.')
      }
    } catch {
      setEmailStatus('error')
      setEmailError('Could not reach the email service — check your connection.')
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-sm font-semibold text-text-primary">Review & Concurrency</p>
        <p className="mt-0.5 text-xs text-text-secondary">
          Confirm there are no conflicting initiatives, review the full configuration, and sign off on launch.
        </p>
      </div>

      {/* ─── Section 1: Concurrent Initiative Collision Radar ─── */}
      {rollout.rolloutScope === 'partial_rollout' && !hasCollisions && (
        <div className="flex items-center gap-2 rounded-[8px] border border-green-500/30 bg-green-50/5 px-4 py-3">
          <AppIcon icon={ShieldCheck} size="sm" className="text-green-600" />
          <p className="text-sm font-medium text-green-700">Zero Store Collisions Detected</p>
        </div>
      )}

      {hasCollisions && (
        <div className="rounded-[8px] border border-amber-500/30 bg-amber-50/5 px-4 py-4">
          <div className="flex items-center gap-2">
            <AppIcon icon={ShieldAlert} size="sm" className="text-amber-600" />
            <p className="text-sm font-semibold text-text-primary">Concurrent Store Initiatives Detected</p>
          </div>
          <p className="mt-1 text-xs text-text-secondary">
            {collisions.collidingStoresCount} of your {collisions.totalTargetStores} Target Stores have
            overlapping projects scheduled
          </p>

          <div className="mt-3 overflow-hidden rounded-xs border border-border-muted/20">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-hover/60">
                <tr>
                  <th className="px-2.5 py-1.5 font-medium text-text-secondary">
                    <span className="sr-only">Select</span>
                  </th>
                  <th className="px-2.5 py-1.5 font-medium text-text-secondary">Initiative Name</th>
                  <th className="px-2.5 py-1.5 font-medium text-text-secondary">Archetype</th>
                  <th className="px-2.5 py-1.5 font-medium text-text-secondary">Overlapping Stores</th>
                  <th className="px-2.5 py-1.5 font-medium text-text-secondary">Overlap Window</th>
                  <th className="px-2.5 py-1.5 font-medium text-text-secondary">Overlap Type</th>
                </tr>
              </thead>
              <tbody>
                {collisions.overlappingInitiatives.map((init) => {
                  const isSelected = review.selectedInitiativeIds.includes(init.initiativeId)
                  return (
                    <tr key={init.initiativeId} className="border-t border-border-muted/15">
                      <td className="px-2.5 py-1.5">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-current"
                          checked={isSelected}
                          onChange={() =>
                            onChange({
                              selectedInitiativeIds: isSelected
                                ? review.selectedInitiativeIds.filter((id) => id !== init.initiativeId)
                                : [...review.selectedInitiativeIds, init.initiativeId],
                            })
                          }
                        />
                      </td>
                      <td className="px-2.5 py-1.5 text-text-primary">{init.initiativeName}</td>
                      <td className="px-2.5 py-1.5 text-text-secondary">{init.archetype}</td>
                      <td className="px-2.5 py-1.5 tabular-nums text-text-primary">
                        {init.impactedStoreCount.toLocaleString()} Stores
                      </td>
                      <td className="px-2.5 py-1.5 text-text-secondary">
                        {formatDateRange(init.startDate, init.endDate)}
                      </td>
                      <td className="px-2.5 py-1.5 text-text-secondary">{OVERLAP_TYPE_LABELS[init.overlapType]}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {review.selectedInitiativeIds.length > 0 && (
            <div className="mt-3">
              <p className="type-overline mb-1.5">Confounder Matrix</p>
              <div className="overflow-hidden rounded-xs border border-border-muted/20">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-hover/60">
                    <tr>
                      <th className="px-2.5 py-1.5 font-medium text-text-secondary">Co-Running Test</th>
                      <th className="px-2.5 py-1.5 font-medium text-text-secondary">Dosage</th>
                      <th className="px-2.5 py-1.5 font-medium text-text-secondary">Attached Resolution Model</th>
                    </tr>
                  </thead>
                  <tbody>
                    {collisions.overlappingInitiatives
                      .filter((init) => review.selectedInitiativeIds.includes(init.initiativeId))
                      .map((init) => (
                        <tr key={init.initiativeId} className="border-t border-border-muted/15">
                          <td className="px-2.5 py-1.5 text-text-primary">{init.initiativeName}</td>
                          <td className="px-2.5 py-1.5 text-text-secondary">{init.dosageDescription}</td>
                          <td className="px-2.5 py-1.5 text-text-secondary">
                            {COLLISION_STRATEGY_OPTIONS.find((o) => o.value === review.collisionHandlingStrategy)?.label}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <p className="mt-3 type-overline">Conflict Resolution</p>
          <div className="mt-1.5 flex flex-col gap-2">
            {COLLISION_STRATEGY_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className="flex cursor-pointer items-start gap-2 rounded-xs px-2 py-1.5 hover:bg-surface-hover"
              >
                <input
                  type="radio"
                  name="collisionStrategy"
                  className="mt-0.5 h-3.5 w-3.5 accent-current"
                  checked={review.collisionHandlingStrategy === opt.value}
                  onChange={() => onChange({ collisionHandlingStrategy: opt.value as CollisionHandlingStrategy })}
                />
                <span className="min-w-0">
                  <span className="block text-xs font-medium text-text-primary">{opt.label}</span>
                  <span className="block text-micro text-text-secondary">{opt.helper}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* ─── Section 2: Executive Blueprint Summary ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <p className="type-overline mb-2">Pre-Launch Executive Blueprint</p>
        <div className="overflow-hidden rounded-xs border border-border-muted/20">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-hover/60">
              <tr>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Wizard Stage</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Parameter</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Value / Status</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['1. Hypothesis', 'Initiative Name', hypothesisName || '—'],
                ['2. Opportunity Sizing', 'Projected Net ROI', formatCurrency(projectedNetRoi)],
                ['3. Metrics', 'Primary KPI', primaryKpiLabel || '—'],
                ['4. Rollout Strategy', 'Target Cohort Scope', cohortScopeLabel(rollout)],
                ['4. Rollout Strategy', 'Control Match Method', controlMethodLabel(rollout)],
                ['4. Rollout Strategy', 'Deployment Schedule', deploymentScheduleLabel(rollout)],
                [
                  '5. Power',
                  'Statistical Viability',
                  `${adequatelyPowered ? 'ADEQUATELY POWERED \u2705' : 'UNDERPOWERED \u26A0\uFE0F'} (Target Lift ${targetLiftPercent.toFixed(1)}% ${adequatelyPowered ? '>' : '<'} MDE ${mdePercent.toFixed(1)}%)`,
                ],
              ].map(([stage, param, value], i) => (
                <tr key={i} className="border-t border-border-muted/15">
                  <td className="px-2.5 py-1.5 text-text-secondary">{stage}</td>
                  <td className="px-2.5 py-1.5 text-text-primary">{param}</td>
                  <td className="px-2.5 py-1.5 font-medium text-text-primary">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Reconciliation to Actuals & Net Lift ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <p className="type-overline mb-2">Reconciliation to Actuals</p>
        <p className="mb-2 text-micro text-text-secondary leading-relaxed">
          Confirms baseline sales plus all active initiative lifts sum back to realized chain sales —
          any gap is surfaced as residual (unmeasured) variance rather than hidden inside a single number.
        </p>
        <div className="overflow-hidden rounded-xs border border-border-muted/20">
          <table className="w-full text-left text-xs">
            <tbody>
              <tr className="border-t border-border-muted/15 first:border-t-0">
                <td className="px-2.5 py-1.5 text-text-secondary">Baseline Chain Sales</td>
                <td className="px-2.5 py-1.5 text-right font-medium text-text-primary tabular-nums">{formatCurrency(reconciliation.baselineChainSales)}</td>
              </tr>
              <tr className="border-t border-border-muted/15">
                <td className="px-2.5 py-1.5 text-text-secondary">+ This Initiative's Lift</td>
                <td className="px-2.5 py-1.5 text-right font-medium text-green-700 tabular-nums">{formatCurrency(reconciliation.thisInitiativeLift)}</td>
              </tr>
              <tr className="border-t border-border-muted/15">
                <td className="px-2.5 py-1.5 text-text-secondary">+ Other Active Initiatives' Lift</td>
                <td className="px-2.5 py-1.5 text-right font-medium text-green-700 tabular-nums">{formatCurrency(reconciliation.otherActiveInitiativesLift)}</td>
              </tr>
              <tr className="border-t border-border-muted/15">
                <td className="px-2.5 py-1.5 text-text-secondary">± Residual (Unmeasured) Variance</td>
                <td className="px-2.5 py-1.5 text-right font-medium text-amber-700 tabular-nums">
                  {formatCurrency(reconciliation.residualVariance)} ({reconciliation.residualVariancePercent.toFixed(2)}%)
                </td>
              </tr>
              <tr className="border-t border-border-muted/25 bg-surface-hover/40">
                <td className="px-2.5 py-2 font-semibold text-text-primary">= Realized Chain Sales</td>
                <td className="px-2.5 py-2 text-right font-bold text-text-primary tabular-nums">{formatCurrency(reconciliation.realizedChainSales)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Section 3: Pre-Flight Launch Sign-Off ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <p className="type-overline mb-2">Pre-Flight Launch Sign-Off</p>
        <div className="flex flex-col gap-3">
          <div>
            <label className="type-caption mb-0.5 block">
              Business Owner Email <span className="text-red-600">*</span>
            </label>
            <input
              type="email"
              className={inputClass}
              placeholder="e.g., j.doe@yourcompany.com"
              value={review.businessOwnerEmail}
              onChange={(e) => onChange({ businessOwnerEmail: e.target.value })}
            />
          </div>
          <div>
            <label className="type-caption mb-0.5 block">Launch Notes (Optional)</label>
            <textarea
              className={`${inputClass} min-h-[70px] resize-y`}
              placeholder="Any operational context for the store ops team…"
              value={review.experimentNotes}
              onChange={(e) => onChange({ experimentNotes: e.target.value })}
            />
          </div>

          <button
            type="button"
            onClick={handleDeployClick}
            disabled={!formValid || isDeploying}
            className="focus-ring flex items-center justify-center gap-2 rounded-xs bg-border-muted px-4 py-2.5 text-sm font-semibold uppercase tracking-wide text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            🚀 Deploy Experiment to Store Fleet
          </button>
          {!formValid && (
            <p className="text-micro text-text-secondary">
              Enter a valid business owner email to enable deployment.
            </p>
          )}
          {emailStatus === 'sending' && (
            <p className="text-micro text-text-secondary">Sending sign-off email…</p>
          )}
          {emailStatus === 'sent' && (
            <p className="flex items-center gap-1.5 text-micro text-green-700">
              <AppIcon icon={CheckCircle2} size="xs" />
              Sign-off email sent to {review.businessOwnerEmail}
            </p>
          )}
          {emailStatus === 'error' && (
            <p className="text-micro text-red-600">
              Email not sent — {emailError}
            </p>
          )}
        </div>
      </div>

      {/* Confirmation modal */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-md rounded-[10px] bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between">
              <p className="text-sm font-semibold text-text-primary">Confirm Experiment Deployment</p>
              <button
                type="button"
                onClick={() => setShowConfirm(false)}
                className="focus-ring text-text-secondary hover:text-text-primary"
              >
                <AppIcon icon={X} size="sm" />
              </button>
            </div>
            <p className="mt-2 text-xs text-text-secondary leading-relaxed">
              This will register the initiative in the Store Operations calendar and activate
              automated baseline performance tracking. Proceed?
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowConfirm(false)}
                className="focus-ring rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-hover"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDeploy}
                className="focus-ring flex items-center gap-1.5 rounded-xs bg-border-muted px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
              >
                <AppIcon icon={CheckCircle2} size="xs" />
                Confirm & Deploy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
