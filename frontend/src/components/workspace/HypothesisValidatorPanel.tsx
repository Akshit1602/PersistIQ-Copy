import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Check, ChevronLeft, ChevronRight, ChevronsRight, Info, Sparkles, X } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { buildBriefBody } from '../../data/briefBuilder'
import {
  createEmptyValidatorDraft,
  draftToModuleSnapshots,
  isStepValid,
  OPPORTUNITY_AUTO_DETECTED,
  POWER_AUTO_DETECTED,
  seedDerivedTypeFromDraft,
  VALIDATOR_STEPS,
  type HypothesisValidatorDraft,
  type ValidatorStepIndex,
} from '../../data/hypothesisValidatorDraft'
import type { ExperimentTypeChoice } from '../../context/types'
import { NumericSliderField } from '../shared/NumericSliderField'
import { AppIcon } from '../shared/AppIcon'
import { MultiSelectDropdown } from '../shared/MultiSelectDropdown'
import { StoreHypothesisExtras } from './StoreHypothesisExtras'
import { STORE_HYPOTHESIS_EXTRAS_DEFAULTS } from '../../data/storeHypothesisExtras'
import { StoreOpportunitySizingStep } from './StoreOpportunitySizingStep'
import { StoreMetricsStep } from './StoreMetricsStep'
import { StoreRolloutTargetingStep } from './StoreRolloutTargetingStep'
import { StorePowerStep } from './StorePowerStep'
import {
  STORE_OPPORTUNITY_DEFAULTS,
  STORE_VALIDATOR_STEPS,
  type StoreValidatorStepIndex,
} from '../../data/storeHypothesisValidator'
import {
  STORE_ROLLOUT_DEFAULTS,
  isStoreRolloutValid,
  type StoreRolloutTargeting,
} from '../../data/storeRolloutTargeting'
import {
  STORE_POWER_DEFAULTS,
  type StorePowerConfig,
} from '../../data/storePowerGuardrails'
import { StoreReviewStep } from './StoreReviewStep'
import {
  STORE_CONCURRENCY_REVIEW_DEFAULTS,
  isConcurrencyReviewValid,
  type ConcurrencyReviewState,
} from '../../data/storeConcurrencyReview'
import { STORE_METRIC_BY_ID } from '../../data/storeMetricCatalog'
import { computeStoreOpportunityOutputs } from '../../data/storeHypothesisValidator'

/** Union covering both the digital (1-5) and store (1-6) step sequences. */
type AnyValidatorStepIndex = ValidatorStepIndex | StoreValidatorStepIndex
import { StepTransitionOverlay } from '../shared/StepTransitionOverlay'
import { SynthesisProgressOverlay } from '../shared/SynthesisProgressOverlay'
import {
  getKpisForRole,
  getMetricInputsForSelection,
  METRIC_KPI_BY_ID,
} from '../../data/metricCatalog'

type PendingStepAdvance = {
  nextStep: AnyValidatorStepIndex
  nextDraft?: HypothesisValidatorDraft
}

function FieldLabel({
  children,
  required = false,
}: {
  children: ReactNode
  required?: boolean
}) {
  return (
    <label className="type-overline mb-1 block">
      {children}
      {required ? (
        <span className="ml-0.5 text-red-600" aria-label="required">
          *
        </span>
      ) : null}
    </label>
  )
}

function SoftFieldLabel({
  children,
  required = false,
  info,
}: {
  children: ReactNode
  required?: boolean
  info?: string
}) {
  return (
    <p className="type-caption mb-0.5 flex min-w-0 items-start gap-1">
      <span className="min-w-0 leading-snug">
        {children}
        {required ? (
          <span className="ml-0.5 text-red-600" aria-label="required">
            *
          </span>
        ) : null}
      </span>
      {info ? (
        <span className="group relative inline-flex shrink-0 pt-0.5">
          <button
            type="button"
            className="focus-ring inline-flex h-4 w-4 items-center justify-center rounded-full text-text-secondary transition-colors hover:text-border-muted"
            aria-label={info}
          >
            <AppIcon icon={Info} size="xs" />
          </button>
          <span
            role="tooltip"
            className="pointer-events-none absolute right-0 top-full z-30 mt-1.5 w-[200px] rounded-xs border border-border-muted/20 bg-text-primary px-2 py-1.5 text-left text-micro font-normal leading-snug text-white opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
          >
            {info}
          </span>
        </span>
      ) : null}
    </p>
  )
}

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
const textareaClass = `${inputClass} resize-none`
const selectClass = `${inputClass} w-full max-w-[45%] appearance-none bg-[length:12px_12px] bg-[right_0.75rem_center] bg-no-repeat pr-9`
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"

function AutoDetectNumberInput({
  value,
  detectedValue,
  detectedHint,
  onChange,
  min,
  max,
  step,
  clearValue = 0,
}: {
  value: number
  detectedValue: number
  detectedHint: string
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  clearValue?: number
}) {
  const [applied, setApplied] = useState(false)

  useEffect(() => {
    if (applied && Number(value) !== Number(detectedValue)) {
      setApplied(false)
    }
  }, [value, detectedValue, applied])

  return (
    <div className="relative">
      <input
        type="number"
        className={`${inputClass} pr-9`}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
      />
      <button
        type="button"
        onClick={() => {
          if (applied) {
            onChange(clearValue)
            setApplied(false)
            return
          }
          onChange(detectedValue)
          setApplied(true)
        }}
        className="focus-ring absolute inset-y-0 right-1 my-auto flex h-6 w-6 items-center justify-center rounded-xs text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
        title={applied ? 'Clear auto-detected value' : `Apply auto-detected: ${detectedHint}`}
        aria-label={applied ? 'Clear auto-detected value' : `Apply auto-detected value ${detectedHint}`}
      >
        <AppIcon icon={applied ? X : Sparkles} size="xs" />
      </button>
    </div>
  )
}

export function HypothesisValidatorPanel() {
  const {
    hypothesisValidatorOpen,
    hypothesisValidatorInitialStep,
    closeHypothesisValidator,
    finalizeHypothesisValidator,
    projects,
    selectedProjectId,
  } = useMatchView()
  const channel = projects.find((p) => p.id === selectedProjectId)?.channel ?? 'digital'
  const [step, setStep] = useState<AnyValidatorStepIndex>(1)
  const [draft, setDraft] = useState<HypothesisValidatorDraft>(createEmptyValidatorDraft)
  const [visible, setVisible] = useState(false)
  const [synthesizing, setSynthesizing] = useState(false)
  const [pendingAdvance, setPendingAdvance] = useState<PendingStepAdvance | null>(null)
  const draftRef = useRef(draft)
  draftRef.current = draft
  const finalizeRef = useRef(finalizeHypothesisValidator)
  finalizeRef.current = finalizeHypothesisValidator
  const pendingAdvanceRef = useRef(pendingAdvance)
  pendingAdvanceRef.current = pendingAdvance
  const isBusy = synthesizing || pendingAdvance !== null

  useEffect(() => {
    if (hypothesisValidatorOpen) {
      setVisible(true)
      return
    }
    const t = window.setTimeout(() => setVisible(false), 220)
    return () => window.clearTimeout(t)
  }, [hypothesisValidatorOpen])

  // Jump to a specific step when opened via "Edit" from Analytics Lab
  useEffect(() => {
    if (hypothesisValidatorOpen && hypothesisValidatorInitialStep != null) {
      setStep(hypothesisValidatorInitialStep as AnyValidatorStepIndex)
    }
  }, [hypothesisValidatorOpen, hypothesisValidatorInitialStep])

  useEffect(() => {
    if (!hypothesisValidatorOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (synthesizing) {
          const ok = window.confirm('Synthesis in progress. Close and cancel?')
          if (!ok) return
        }
        if (pendingAdvance) return
        handleClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hypothesisValidatorOpen, synthesizing, pendingAdvance])

  const storeRollout: StoreRolloutTargeting = (draft as any).storeRollout ?? STORE_ROLLOUT_DEFAULTS
  const storePower: StorePowerConfig = (draft as any).storePower ?? STORE_POWER_DEFAULTS
  const storeConcurrencyReview: ConcurrencyReviewState =
    (draft as any).storeConcurrencyReview ?? STORE_CONCURRENCY_REVIEW_DEFAULTS

  const canNext =
    channel === 'store'
      ? step === 3
        ? isStoreRolloutValid(storeRollout)
        : step === 4
          ? isStepValid(draft, 3 as ValidatorStepIndex) // reuses the shared metrics-required-fields check
          : step === 5
            ? storePower.aaTestResult ? storePower.aaTestResult.passed : true // hard-blocked if A/A test failed
            : step === 6
              ? Boolean(draft.derivedExperimentType && draft.typeRationale) &&
                isConcurrencyReviewValid(storeConcurrencyReview)
              : isStepValid(draft, step as ValidatorStepIndex)
      : isStepValid(draft, step as ValidatorStepIndex)

  const resetDraft = () => {
    setStep(1)
    setDraft(createEmptyValidatorDraft())
    setSynthesizing(false)
    setPendingAdvance(null)
  }

  const handleClose = () => {
    if (isBusy) return
    closeHypothesisValidator()
    window.setTimeout(resetDraft, 220)
  }

  const queueAdvance = (next: PendingStepAdvance) => {
    if (isBusy) return
    setPendingAdvance(next)
  }

  const completeStepTransition = useCallback(() => {
    const pending = pendingAdvanceRef.current
    if (!pending) return
    if (pending.nextDraft) setDraft(pending.nextDraft)
    setStep(pending.nextStep)
    setPendingAdvance(null)
  }, [])

  const goNext = () => {
    if (!canNext || isBusy) return
    if (step === 1) {
      queueAdvance({ nextStep: 2 })
      return
    }
    if (step === 2) {
      queueAdvance({
        nextStep: 3,
        nextDraft: {
          ...draft,
          opportunity: { ...draft.opportunity, skipped: false },
        },
      })
      return
    }
    if (channel === 'store') {
      // Store sequence: 1 Hypothesis -> 2 Sizing -> 3 Rollout -> 4 Metrics -> 5 Power -> 6 Review
      if (step === 3) {
        queueAdvance({ nextStep: 4 })
        return
      }
      if (step === 4) {
        queueAdvance({ nextStep: 5 })
        return
      }
      if (step === 5) {
        queueAdvance({ nextStep: 6, nextDraft: seedDerivedTypeFromDraft(draft) })
        return
      }
      return
    }
    // Digital sequence: 1 Hypothesis -> 2 Sizing -> 3 Metrics -> 4 Power -> 5 Review
    if (step === 3) {
      queueAdvance({ nextStep: 4 })
      return
    }
    if (step === 4) {
      queueAdvance({
        nextStep: 5,
        nextDraft: seedDerivedTypeFromDraft(draft),
      })
    }
  }

  const skipOpportunity = () => {
    if (isBusy) return
    queueAdvance({
      nextStep: 3,
      nextDraft: {
        ...draft,
        opportunity: { ...draft.opportunity, skipped: true },
      },
    })
  }

  const goBack = () => {
    if (step > 1 && !isBusy) setStep((s) => (s - 1) as AnyValidatorStepIndex)
  }

  const runFinalize = useCallback(() => {
    const typed = seedDerivedTypeFromDraft(draftRef.current)
    const snapshots = draftToModuleSnapshots(typed)
    const spec = {
      name: typed.name.trim(),
      hypothesis: typed.hypothesis.trim(),
      goal: typed.goal.trim(),
      channel: 'digital' as const,
      experimentType: typed.derivedExperimentType,
      typeRationale: typed.typeRationale,
      metricsApproved: true,
    }
    const briefBody = buildBriefBody(spec, snapshots)
    const briefTitle = `${spec.name} — Digital Experiment Brief`

    finalizeRef.current({
      name: spec.name,
      hypothesis: spec.hypothesis,
      goal: spec.goal,
      opportunity: snapshots['opportunity-sizing']!,
      metrics: snapshots['metrics-tracking']!,
      experimentType: snapshots['experiment-type']!,
      power: snapshots['power-calculator']!,
      briefTitle,
      briefBody,
      metricsApproved: true,
      experimentTypeChoice: typed.derivedExperimentType,
      typeRationale: typed.typeRationale,
      opportunitySkipped: typed.opportunity.skipped,
    })

    resetDraft()
  }, [])

  const handleGetStarted = () => {
    const finalStepValid =
      channel === 'store'
        ? Boolean(draft.derivedExperimentType && draft.typeRationale) &&
          isConcurrencyReviewValid(storeConcurrencyReview)
        : isStepValid(draft, 5)
    if (!finalStepValid || isBusy) return
    setSynthesizing(true)
  }

  const patch = useMemo(
    () => ({
      opportunity: (partial: Partial<HypothesisValidatorDraft['opportunity']>) =>
        setDraft((d) => ({ ...d, opportunity: { ...d.opportunity, ...partial } })),
      metrics: (partial: Partial<HypothesisValidatorDraft['metrics']>) =>
        setDraft((d) => ({ ...d, metrics: { ...d.metrics, ...partial } })),
      power: (partial: Partial<HypothesisValidatorDraft['power']>) =>
        setDraft((d) => ({ ...d, power: { ...d.power, ...partial } })),
    }),
    [],
  )

  const activeSteps = channel === 'store' ? STORE_VALIDATOR_STEPS : VALIDATOR_STEPS

  if (!visible && !hypothesisValidatorOpen) return null

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <button
        type="button"
        className={`absolute inset-0 bg-black/30 transition-opacity duration-200 ${
          hypothesisValidatorOpen ? 'opacity-100' : 'opacity-0'
        }`}
        onClick={handleClose}
        disabled={isBusy}
        aria-label="Close hypothesis validator"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="hypothesis-validator-panel-title"
        className={`relative flex h-full w-full max-w-[640px] flex-col overflow-hidden border-l border-border-muted/20 bg-surface-raised shadow-glow transition-transform duration-200 ease-out ${
          hypothesisValidatorOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <StepTransitionOverlay
          active={pendingAdvance !== null}
          onComplete={completeStepTransition}
          title="Loading next step"
          subtitle="Fetching data for your setup…"
        />
        <SynthesisProgressOverlay active={synthesizing} onComplete={runFinalize} />

        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-muted/20 px-4 py-3.5">
          <div>
            <h2
              id="hypothesis-validator-panel-title"
              className="type-title"
            >
              Initiative Setup & Benchmarking
            </h2>
            <p className="mt-0.5 text-xs text-text-secondary">
              {channel === 'store' ? 'Store' : 'Digital'} experiment setup — Opportunity is optional. Audience comes after the brief.
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={isBusy}
            className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary disabled:opacity-40"
            aria-label="Close"
          >
            <AppIcon icon={X} size="sm" />
          </button>
        </header>

        <nav
          className="shrink-0 border-b border-border-muted/15 px-4 py-3"
          aria-label="Setup steps"
        >
          <ol className="flex w-full items-start">
            {activeSteps.map((s, index) => {
              const done = s.id < step
              const active = s.id === step
              const incomingComplete = s.id <= step
              const outgoingComplete = s.id < step
              return (
                <li key={s.id} className="relative min-w-0 flex-1">
                  <div
                    className={`flex flex-col items-center gap-1 rounded-xs px-1 py-1.5 text-center ${
                      active ? 'bg-border-muted/10' : ''
                    }`}
                  >
                    <div className="relative flex h-6 w-full items-center justify-center">
                      {index > 0 ? (
                        <span
                          className={`absolute inset-y-0 left-0 right-1/2 my-auto h-px ${
                            incomingComplete ? 'bg-border-muted' : 'bg-border-muted/25'
                          }`}
                          aria-hidden="true"
                        />
                      ) : null}
                      {index < activeSteps.length - 1 ? (
                        <span
                          className={`absolute inset-y-0 left-1/2 right-0 my-auto h-px ${
                            outgoingComplete ? 'bg-border-muted' : 'bg-border-muted/25'
                          }`}
                          aria-hidden="true"
                        />
                      ) : null}
                      <span
                        className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-micro font-semibold ${
                          done
                            ? 'bg-border-muted text-white'
                            : active
                              ? 'border border-border-muted bg-surface-raised text-border-muted'
                              : 'border border-border-muted/30 bg-surface-raised text-text-secondary'
                        }`}
                      >
                        {done ? <AppIcon icon={Check} size="xs" /> : s.id}
                      </span>
                    </div>
                    <span
                      className={`w-full text-center text-micro font-medium leading-tight ${
                        active ? 'text-text-primary' : 'text-text-secondary'
                      }`}
                      title={s.label}
                    >
                      {s.short}
                    </span>
                  </div>
                </li>
              )
            })}
          </ol>
        </nav>

        <div className="relative min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-4">
          {step === 1 && (
            <div className="flex flex-col gap-3.5">
              <div>
                <FieldLabel required>Name</FieldLabel>
                <input
                  className={inputClass}
                  value={draft.name}
                  onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                  placeholder="e.g. Checkout Flow Redesign"
                  autoFocus
                />
              </div>
              <div>
                <FieldLabel required>Hypothesis</FieldLabel>
                <textarea
                  className={textareaClass}
                  rows={4}
                  value={draft.hypothesis}
                  onChange={(e) => setDraft((d) => ({ ...d, hypothesis: e.target.value }))}
                  placeholder={`If we change X for ${channel === 'store' ? 'store' : 'digital'} users, then Y will improve because…`}
                />
              </div>
              {channel === 'store' && (
                <StoreHypothesisExtras
                  extras={(draft as any).storeHypothesisExtras ?? STORE_HYPOTHESIS_EXTRAS_DEFAULTS}
                  hypothesisName={draft.name}
                  onChange={(partial) =>
                    setDraft((d) => ({
                      ...d,
                      storeHypothesisExtras: {
                        ...((d as any).storeHypothesisExtras ?? STORE_HYPOTHESIS_EXTRAS_DEFAULTS),
                        ...partial,
                      },
                    }))
                  }
                />
              )}
            </div>
          )}

          {step === 2 && channel === 'store' && (
            <StoreOpportunitySizingStep
              inputs={(draft as any).storeOpportunity ?? STORE_OPPORTUNITY_DEFAULTS}
              onChange={(partial) =>
                setDraft((d) => ({
                  ...d,
                  storeOpportunity: { ...((d as any).storeOpportunity ?? STORE_OPPORTUNITY_DEFAULTS), ...partial },
                }))
              }
            />
          )}

          {step === 2 && channel !== 'store' && (
            <div className="flex flex-col gap-3.5">
              <div>
                <p className="text-sm font-semibold text-text-primary">Opportunity Sizing</p>
                <p className="mt-0.5 text-xs text-text-secondary">
                  Quantify the revenue opportunity before committing to an experiment.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <FieldLabel>Monthly inquiries</FieldLabel>
                  <AutoDetectNumberInput
                    value={draft.opportunity.monthlyInquiries}
                    detectedValue={OPPORTUNITY_AUTO_DETECTED.monthlyInquiries}
                    detectedHint={`${OPPORTUNITY_AUTO_DETECTED.monthlyInquiries.toLocaleString()}/month`}
                    min={0}
                    step={100}
                    onChange={(monthlyInquiries) =>
                      patch.opportunity({ monthlyInquiries, skipped: false })
                    }
                  />
                </div>

                <div className="min-w-0">
                  <FieldLabel>Average order value ($)</FieldLabel>
                  <AutoDetectNumberInput
                    value={draft.opportunity.aov}
                    detectedValue={OPPORTUNITY_AUTO_DETECTED.aov}
                    detectedHint={`$${OPPORTUNITY_AUTO_DETECTED.aov.toLocaleString()}`}
                    min={0}
                    step={1}
                    onChange={(aov) => patch.opportunity({ aov, skipped: false })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <FieldLabel>Current IOR (0–1)</FieldLabel>
                  <AutoDetectNumberInput
                    value={draft.opportunity.currentIor}
                    detectedValue={OPPORTUNITY_AUTO_DETECTED.currentIor}
                    detectedHint={OPPORTUNITY_AUTO_DETECTED.currentIor.toFixed(4)}
                    min={0}
                    max={1}
                    step={0.0001}
                    onChange={(currentIor) => patch.opportunity({ currentIor, skipped: false })}
                  />
                </div>

                <div className="min-w-0">
                  <FieldLabel>Target IOR after experiment</FieldLabel>
                  <input
                    type="number"
                    className={inputClass}
                    value={draft.opportunity.targetIor}
                    min={0}
                    max={1}
                    step={0.0001}
                    onChange={(e) =>
                      patch.opportunity({
                        targetIor: Number(e.target.value) || 0,
                        skipped: false,
                      })
                    }
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <FieldLabel>Gross margin (0–1)</FieldLabel>
                  <NumericSliderField
                    aria-label="Gross margin"
                    value={draft.opportunity.grossMargin}
                    min={0}
                    max={1}
                    step={0.01}
                    formatValue={(v) => `${Math.round(v * 100)}%`}
                    onChange={(grossMargin) =>
                      patch.opportunity({ grossMargin, skipped: false })
                    }
                  />
                </div>

                <div className="min-w-0">
                  <FieldLabel>Time horizon (months)</FieldLabel>
                  <NumericSliderField
                    aria-label="Time horizon in months"
                    value={draft.opportunity.timeHorizonMonths}
                    min={1}
                    max={36}
                    step={1}
                    formatValue={(v) => `${v} mo`}
                    onChange={(timeHorizonMonths) =>
                      patch.opportunity({ timeHorizonMonths, skipped: false })
                    }
                  />
                </div>
              </div>
            </div>
          )}

          {step === 3 && channel === 'store' && (
            <StoreRolloutTargetingStep
              rollout={storeRollout}
              onChange={(partial) =>
                setDraft((d) => ({
                  ...d,
                  storeRollout: { ...((d as any).storeRollout ?? STORE_ROLLOUT_DEFAULTS), ...partial },
                }))
              }
            />
          )}

          {step === 4 && channel === 'store' && (
            <StoreMetricsStep
              metrics={draft.metrics}
              onChange={(partial) =>
                setDraft((d) => ({ ...d, metrics: { ...d.metrics, ...partial } }))
              }
            />
          )}

          {step === 3 && channel !== 'store' && (
            <div className="flex flex-col gap-3.5">
              <div>
                <p className="text-sm font-semibold text-text-primary">Metrics And Tracking</p>
                <p className="mt-0.5 text-xs text-text-secondary">
                  Select primary, secondary, and guardrail KPIs. Primary/secondary may ask for
                  baselines and tracking events.
                </p>
              </div>

              <div>
                <SoftFieldLabel required>Primary metrics</SoftFieldLabel>
                <p className="mb-1 text-micro text-text-secondary">
                  Success KPIs for the hypothesis — at least one required
                </p>
                <MultiSelectDropdown
                  aria-label="Primary metrics"
                  placeholder="Select primary KPIs…"
                  options={getKpisForRole('primary').map((k) => ({
                    id: k.id,
                    label: k.label,
                    description: k.description,
                    disabled: draft.metrics.secondaryMetricIds.includes(k.id),
                  }))}
                  value={draft.metrics.primaryMetricIds}
                  onChange={(primaryMetricIds) => {
                    const dropped = draft.metrics.primaryMetricIds.filter(
                      (id) => !primaryMetricIds.includes(id),
                    )
                    const metricInputs = { ...draft.metrics.metricInputs }
                    for (const id of dropped) delete metricInputs[id]
                    patch.metrics({ primaryMetricIds, metricInputs })
                  }}
                />
              </div>

              <div>
                <SoftFieldLabel>Secondary metrics</SoftFieldLabel>
                <p className="mb-1 text-micro text-text-secondary">
                  Supporting signals — optional
                </p>
                <MultiSelectDropdown
                  aria-label="Secondary metrics"
                  placeholder="Select secondary KPIs…"
                  options={getKpisForRole('secondary').map((k) => ({
                    id: k.id,
                    label: k.label,
                    description: k.description,
                    disabled: draft.metrics.primaryMetricIds.includes(k.id),
                  }))}
                  value={draft.metrics.secondaryMetricIds}
                  onChange={(secondaryMetricIds) => {
                    const dropped = draft.metrics.secondaryMetricIds.filter(
                      (id) => !secondaryMetricIds.includes(id),
                    )
                    const metricInputs = { ...draft.metrics.metricInputs }
                    for (const id of dropped) delete metricInputs[id]
                    patch.metrics({ secondaryMetricIds, metricInputs })
                  }}
                />
              </div>

              {getMetricInputsForSelection([
                ...draft.metrics.primaryMetricIds,
                ...draft.metrics.secondaryMetricIds,
              ]).length > 0 ? (
                <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/70 px-3 py-3">
                  <p className="type-overline mb-2">KPI inputs</p>
                  <p className="mb-3 text-micro text-text-secondary">
                    Provide baselines and tracking events for the selected primary/secondary KPIs.
                  </p>
                  <div className="flex flex-col gap-3.5">
                    {getMetricInputsForSelection([
                      ...draft.metrics.primaryMetricIds,
                      ...draft.metrics.secondaryMetricIds,
                    ]).map(({ kpiId, label, inputs }) => (
                      <div key={kpiId} className="flex flex-col gap-2">
                        <p className="text-xs font-semibold text-text-primary">{label}</p>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          {inputs.map((field) => (
                            <div key={`${kpiId}-${field.key}`} className="min-w-0">
                              <SoftFieldLabel required={field.required !== false}>
                                {field.label}
                              </SoftFieldLabel>
                              <input
                                type={field.type === 'number' ? 'number' : 'text'}
                                className={inputClass}
                                value={draft.metrics.metricInputs[kpiId]?.[field.key] ?? ''}
                                placeholder={field.placeholder}
                                onChange={(e) => {
                                  const next = {
                                    ...draft.metrics.metricInputs,
                                    [kpiId]: {
                                      ...(draft.metrics.metricInputs[kpiId] ?? {}),
                                      [field.key]: e.target.value,
                                    },
                                  }
                                  patch.metrics({ metricInputs: next })
                                }}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div>
                <SoftFieldLabel>Guardrail metrics</SoftFieldLabel>
                <p className="mb-1 text-micro text-text-secondary">
                  Metrics that must not degrade — no extra inputs needed
                </p>
                <MultiSelectDropdown
                  aria-label="Guardrail metrics"
                  placeholder="Select guardrail KPIs…"
                  options={getKpisForRole('guardrail').map((k) => ({
                    id: k.id,
                    label: k.label,
                    description: k.description,
                  }))}
                  value={draft.metrics.guardrailMetricIds}
                  onChange={(guardrailMetricIds) => patch.metrics({ guardrailMetricIds })}
                />
              </div>
            </div>
          )}

          {step === 5 && channel === 'store' && (
            <StorePowerStep
              power={storePower}
              onChange={(partial) =>
                setDraft((d) => ({
                  ...d,
                  storePower: { ...((d as any).storePower ?? STORE_POWER_DEFAULTS), ...partial },
                }))
              }
              targetLiftPercent={
                (((draft as any).storeOpportunity ?? STORE_OPPORTUNITY_DEFAULTS).metrics.targetCvrLift ?? 0) * 100
              }
              storeCount={storeRollout.matchResult?.treatmentGroupSize ?? storeRollout.treatmentFilters.targetStoreCount}
            />
          )}

          {step === 4 && channel !== 'store' && (
            <div className="flex max-w-full flex-col gap-3.5 overflow-hidden">
              <div>
                <p className="text-sm font-semibold text-text-primary">Power Calculator</p>
                <p className="mt-0.5 text-xs text-text-secondary">
                  Calculate required sample size and experiment duration from your baseline data.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <SoftFieldLabel required>Baseline IOR rate (0–1)</SoftFieldLabel>
                  <AutoDetectNumberInput
                    value={draft.power.baselineIor}
                    detectedValue={POWER_AUTO_DETECTED.baselineIor}
                    detectedHint={POWER_AUTO_DETECTED.baselineIor.toFixed(4)}
                    min={0}
                    max={1}
                    step={0.0001}
                    onChange={(baselineIor) => patch.power({ baselineIor })}
                  />
                </div>

                <div className="min-w-0">
                  <SoftFieldLabel
                    required
                    info="e.g. 10 means detect a 10% relative lift"
                  >
                    Minimum detectable effect (% relative)
                  </SoftFieldLabel>
                  <input
                    type="number"
                    className={inputClass}
                    value={draft.power.mdePercent}
                    min={0.1}
                    max={100}
                    step={0.1}
                    onChange={(e) => patch.power({ mdePercent: Number(e.target.value) || 0 })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <SoftFieldLabel required>Significance level α</SoftFieldLabel>
                  <NumericSliderField
                    aria-label="Significance level alpha"
                    value={draft.power.alpha}
                    min={0.01}
                    max={0.2}
                    step={0.01}
                    formatValue={(v) => v.toFixed(2)}
                    onChange={(alpha) => patch.power({ alpha })}
                  />
                </div>

                <div className="min-w-0">
                  <SoftFieldLabel required>Statistical power 1−β</SoftFieldLabel>
                  <NumericSliderField
                    aria-label="Statistical power"
                    value={draft.power.statisticalPower}
                    min={0.5}
                    max={0.99}
                    step={0.01}
                    formatValue={(v) => `${Math.round(v * 100)}%`}
                    onChange={(statisticalPower) => patch.power({ statisticalPower })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <SoftFieldLabel required>Number of variants (incl. control)</SoftFieldLabel>
                  <input
                    type="number"
                    className={inputClass}
                    value={draft.power.variants}
                    min={2}
                    max={10}
                    step={1}
                    onChange={(e) => patch.power({ variants: Number(e.target.value) || 2 })}
                  />
                </div>

                <div className="min-w-0">
                  <SoftFieldLabel required>Daily eligible traffic</SoftFieldLabel>
                  <AutoDetectNumberInput
                    value={draft.power.dailyTraffic}
                    detectedValue={POWER_AUTO_DETECTED.dailyTraffic}
                    detectedHint={`${POWER_AUTO_DETECTED.dailyTraffic} daily inquiries`}
                    min={1}
                    step={1}
                    onChange={(dailyTraffic) => patch.power({ dailyTraffic })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="min-w-0">
                  <SoftFieldLabel required>Traffic fraction in experiment (0–1)</SoftFieldLabel>
                  <input
                    type="number"
                    className={inputClass}
                    value={draft.power.trafficFraction}
                    min={0.01}
                    max={1}
                    step={0.01}
                    onChange={(e) =>
                      patch.power({ trafficFraction: Number(e.target.value) || 0 })
                    }
                  />
                </div>
              </div>
            </div>
          )}

          {step === 6 && channel === 'store' && (
            <StoreReviewStep
              review={storeConcurrencyReview}
              onChange={(partial) =>
                setDraft((d) => ({
                  ...d,
                  storeConcurrencyReview: {
                    ...((d as any).storeConcurrencyReview ?? STORE_CONCURRENCY_REVIEW_DEFAULTS),
                    ...partial,
                  },
                }))
              }
              hypothesisName={draft.name}
              primaryKpiLabel={
                STORE_METRIC_BY_ID[draft.metrics.primaryMetricIds[0]]?.label ?? '—'
              }
              projectedNetRoi={
                computeStoreOpportunityOutputs(
                  (draft as any).storeOpportunity ?? STORE_OPPORTUNITY_DEFAULTS,
                ).projectedNetRoi
              }
              rollout={storeRollout}
              power={storePower}
              targetLiftPercent={
                (((draft as any).storeOpportunity ?? STORE_OPPORTUNITY_DEFAULTS).metrics.targetCvrLift ?? 0) * 100
              }
              onDeploy={handleGetStarted}
              isDeploying={isBusy}
            />
          )}

          {step === 5 && channel !== 'store' && (
            <div className="flex flex-col gap-3.5">
              <div className="rounded-xs border border-border-muted/25 bg-surface-base px-3 py-3">
                <p className="text-micro font-semibold uppercase tracking-wide text-text-secondary">
                  System-derived experiment type
                </p>
                <select
                  className={`${selectClass} mt-2`}
                  style={{ backgroundImage: selectChevronBg }}
                  value={draft.derivedExperimentType}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      derivedExperimentType: e.target.value as ExperimentTypeChoice,
                    }))
                  }
                >
                  <option value="A/B">A/B</option>
                  <option value="A/B/C">A/B/C</option>
                  <option value="Causal">Causal</option>
                </select>
                <p className="mt-2 text-xs leading-relaxed text-text-secondary">
                  {draft.typeRationale}
                </p>
              </div>
              <div className="rounded-xs border border-border-muted/15 px-3 py-2.5 text-xs text-text-secondary">
                <p>
                  <span className="font-medium text-text-primary">Hypothesis:</span>{' '}
                  {draft.name}
                </p>
                <p className="mt-1">
                  <span className="font-medium text-text-primary">Primary:</span>{' '}
                  {draft.metrics.primaryMetricIds
                    .map((id) => METRIC_KPI_BY_ID[id]?.label ?? id)
                    .join(', ') || '—'}
                </p>
                <p className="mt-1">
                  <span className="font-medium text-text-primary">Secondary:</span>{' '}
                  {draft.metrics.secondaryMetricIds
                    .map((id) => METRIC_KPI_BY_ID[id]?.label ?? id)
                    .join(', ') || '—'}
                </p>
                <p className="mt-1">
                  <span className="font-medium text-text-primary">Guardrails:</span>{' '}
                  {draft.metrics.guardrailMetricIds
                    .map((id) => METRIC_KPI_BY_ID[id]?.label ?? id)
                    .join(', ') || '—'}
                </p>
                <p className="mt-1">
                  <span className="font-medium text-text-primary">Opportunity:</span>{' '}
                  {draft.opportunity.skipped
                    ? 'Skipped'
                    : `${draft.opportunity.monthlyInquiries.toLocaleString()} inquiries · IOR ${draft.opportunity.currentIor} → ${draft.opportunity.targetIor}`}
                </p>
              </div>
              <p className="text-xs text-text-secondary">
                Get Started synthesizes the brief. Configure Audience afterward from the brief
                card or Analytics Lab.
              </p>
            </div>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-border-muted/20 px-4 py-3">
          <button
            type="button"
            onClick={goBack}
            disabled={step === 1 || isBusy}
            className="focus-ring inline-flex items-center gap-1 rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            <AppIcon icon={ChevronLeft} size="xs" />
            Back
          </button>
          <div className="flex items-center gap-2">
            {step === 2 ? (
              <button
                type="button"
                onClick={skipOpportunity}
                disabled={isBusy}
                className="focus-ring inline-flex items-center gap-1 rounded-xs border border-border-muted/40 px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-hover disabled:opacity-40"
              >
                Skip Opportunity Sizing
                <AppIcon icon={ChevronsRight} size="xs" />
              </button>
            ) : null}
            {step < (channel === 'store' ? 6 : 5) ? (
              <button
                type="button"
                onClick={goNext}
                disabled={!canNext || isBusy}
                className="focus-ring inline-flex items-center gap-1 rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
                <AppIcon icon={ChevronRight} size="xs" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleGetStarted}
                disabled={!canNext || isBusy}
                className="focus-ring rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Get Started
              </button>
            )}
          </div>
        </footer>
      </aside>
    </div>
  )
}
