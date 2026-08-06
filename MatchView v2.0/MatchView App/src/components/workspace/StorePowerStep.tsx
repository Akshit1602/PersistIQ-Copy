import { useMemo, useState } from 'react'
import { Gauge, CheckCircle2, AlertTriangle, Loader2, FlaskConical, ShieldCheck } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import { InfoTooltip } from '../shared/InfoTooltip'
import {
  type StorePowerConfig,
  type HistoricalLookbackMode,
  type AlphaLevel,
  type PowerLevel,
  LOOKBACK_OPTIONS,
  ALPHA_OPTIONS,
  POWER_OPTIONS,
  computeMde,
  isAdequatelyPowered,
  simulateHistoricalAaTest,
  simulateEmpiricalPower,
} from '../../data/storePowerGuardrails'

interface Props {
  power: StorePowerConfig
  onChange: (partial: Partial<StorePowerConfig>) => void
  targetLiftPercent: number
  storeCount: number
}

const selectClass =
  'focus-ring box-border w-full min-w-0 appearance-none rounded-xs border border-border-muted/25 bg-surface-base bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat px-2.5 py-1.5 pr-8 text-xs text-text-primary'
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"
const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary'

export function StorePowerStep({ power, onChange, targetLiftPercent, storeCount }: Props) {
  const [aaError, setAaError] = useState<string | null>(null)
  const [empiricalError, setEmpiricalError] = useState<string | null>(null)

  const mdePercent = useMemo(
    () => computeMde(power, storeCount) * 100,
    [power, storeCount],
  )
  const adequatelyPowered = isAdequatelyPowered(targetLiftPercent, mdePercent)

  const runEmpiricalPower = async () => {
    setEmpiricalError(null)
    onChange({ isRunningEmpiricalPower: true, empiricalPowerResult: null })
    try {
      const result = await simulateEmpiricalPower(power, storeCount, targetLiftPercent, 750)
      onChange({ isRunningEmpiricalPower: false, empiricalPowerResult: result })
    } catch {
      setEmpiricalError('Empirical simulation failed to run — try again.')
      onChange({ isRunningEmpiricalPower: false })
    }
  }

  const runAaTest = async () => {
    setAaError(null)
    onChange({ isRunningAaTest: true, aaTestResult: null })
    try {
      const result = await simulateHistoricalAaTest(power, storeCount)
      onChange({ isRunningAaTest: false, aaTestResult: result })
    } catch {
      setAaError('A/A validation failed to run — try again.')
      onChange({ isRunningAaTest: false })
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <p className="text-sm font-semibold text-text-primary">Power</p>
        <p className="mt-0.5 text-xs text-text-secondary">
          Confirm the matched store cohort can actually detect the lift you're targeting before launch.
        </p>
      </div>

      {/* Historical Variance Lookback */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <div className="mb-1 flex items-center gap-1.5">
          <label className="type-overline block">Historical Variance Lookback</label>
          <InfoTooltip text="How many weeks of store_performance_weekly history to use for baseline variance (\u03C3). Seasonal matching (same period last year) removes the most noise; recent quarter reacts fastest to changing conditions." />
        </div>
        <select
          className={selectClass}
          style={{ backgroundImage: selectChevronBg }}
          value={power.historicalLookbackMode}
          onChange={(e) =>
            onChange({ historicalLookbackMode: e.target.value as HistoricalLookbackMode })
          }
        >
          {LOOKBACK_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {power.historicalLookbackMode === 'custom' && (
          <div className="mt-2">
            <label className="type-caption mb-0.5 block">Custom Lookback (weeks)</label>
            <input
              type="number"
              className={inputClass}
              min={4}
              max={104}
              placeholder="e.g. 20"
              value={power.customLookbackWeeks ?? ''}
              onChange={(e) => onChange({ customLookbackWeeks: e.target.value === '' ? null : Number(e.target.value) })}
            />
          </div>
        )}
      </div>

      {/* CUPED toggle */}
      <div className="flex items-center justify-between rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <div className="min-w-0 pr-3">
          <div className="flex items-center gap-1.5">
            <p className="type-overline">Apply Variance Reduction (CUPED)</p>
            <InfoTooltip text="Uses pre-experiment store performance covariates to shrink baseline variance — reduces the MDE without requiring additional stores." />
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={power.cupedEnabled}
          onClick={() => onChange({ cupedEnabled: !power.cupedEnabled })}
          className={`focus-ring relative h-5 w-9 shrink-0 rounded-lg transition-colors duration-instant ${
            power.cupedEnabled ? 'bg-border-muted' : 'bg-border-muted/25'
          }`}
        >
          <span
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-instant ${
              power.cupedEnabled ? 'translate-x-[18px]' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>

      {/* Clean KPI cards: Alpha, Beta, MDE, Power */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-2.5">
          <div className="mb-1 flex items-center gap-1.5">
            <p className="type-caption">Alpha (\u03B1)</p>
            <InfoTooltip text="Significance level — the false-positive threshold for the store baseline. Lower alpha means stricter evidence required before declaring a real effect." />
          </div>
          <select
            className={selectClass}
            style={{ backgroundImage: selectChevronBg }}
            value={power.alpha}
            onChange={(e) => onChange({ alpha: Number(e.target.value) as AlphaLevel })}
          >
            {ALPHA_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-2.5">
          <div className="mb-1 flex items-center gap-1.5">
            <p className="type-caption">Beta (\u03B2) / Power</p>
            <InfoTooltip text="Statistical power target (1 - beta) — the probability of detecting a true lift if one exists. Higher power needs more stores or a bigger MDE." />
          </div>
          <select
            className={selectClass}
            style={{ backgroundImage: selectChevronBg }}
            value={power.statisticalPower}
            onChange={(e) => onChange({ statisticalPower: Number(e.target.value) as PowerLevel })}
          >
            {POWER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Dynamic MDE vs Target Lift Comparison Card */}
      <div
        className={`rounded-[8px] border px-4 py-4 ${
          adequatelyPowered ? 'border-green-500/30 bg-green-50/5' : 'border-red-500/30 bg-red-50/5'
        }`}
      >
        <div className="flex items-center gap-2 mb-3">
          <AppIcon icon={Gauge} size="sm" />
          <p className="text-sm font-semibold text-text-primary">Power Viability Analysis</p>
          <InfoTooltip text="MDE (Minimum Detectable Effect) = (z\u03B1/2 + z\u03B2) \u00D7 \u221A(2\u03C3\u00B2/N). If your target lift is below this, the sample size can't reliably detect it." />
          <span className="ml-auto text-micro text-text-secondary italic">Updates live</span>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="rounded-xs bg-surface-raised/60 px-3 py-2.5">
            <p className="text-micro text-text-secondary">Target Expected Lift</p>
            <p className="text-sm font-semibold text-text-primary tabular-nums">
              {targetLiftPercent.toFixed(2)}%
            </p>
            <p className="mt-0.5 text-micro text-text-secondary">from Opportunity Sizing</p>
          </div>
          <div className="rounded-xs bg-surface-raised/60 px-3 py-2.5">
            <p className="text-micro text-text-secondary">Calculated MDE</p>
            <p className="text-sm font-semibold text-text-primary tabular-nums">{mdePercent.toFixed(2)}%</p>
            <p className="mt-0.5 text-micro text-text-secondary">
              {storeCount.toLocaleString()} stores · {power.cupedEnabled ? 'CUPED on' : 'CUPED off'}
            </p>
          </div>
        </div>

        <div
          className={`flex items-center gap-2 rounded-xs px-3 py-2 text-xs font-medium ${
            adequatelyPowered ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}
        >
          <AppIcon icon={adequatelyPowered ? CheckCircle2 : AlertTriangle} size="sm" />
          {adequatelyPowered
            ? 'ADEQUATELY POWERED — Sample size is sufficient to detect target lift.'
            : 'UNDERPOWERED — Increase store count in Rollout step or apply CUPED.'}
        </div>
      </div>

      {/* Historical A/A Sanity Check Simulation */}
      <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
        <div className="flex items-center gap-2">
          <AppIcon icon={FlaskConical} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">Pre-Flight A/A Validation</p>
        </div>
        <p className="mt-1 text-xs text-text-secondary leading-relaxed">
          Runs a mock experiment on the matched stores against historical non-treatment weeks to confirm
          the baseline produces zero false-positive lift.
        </p>
        <button
          type="button"
          onClick={runAaTest}
          disabled={power.isRunningAaTest}
          className="focus-ring mt-3 flex items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {power.isRunningAaTest ? (
            <>
              <AppIcon icon={Loader2} size="xs" className="animate-spin" />
              Running historical A/A test…
            </>
          ) : (
            <>
              <AppIcon icon={ShieldCheck} size="xs" />
              Run Historical A/A Test
            </>
          )}
        </button>
        {aaError && <p className="mt-1.5 text-micro text-red-600">{aaError}</p>}
        {power.aaTestResult && !power.isRunningAaTest && (
          <div
            className={`mt-2.5 rounded-xs px-3 py-2 text-xs font-medium ${
              power.aaTestResult.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}
          >
            <div className="flex items-center gap-2">
              <AppIcon icon={power.aaTestResult.passed ? CheckCircle2 : AlertTriangle} size="sm" />
              Simulated Lift: {power.aaTestResult.simulatedLiftPercent >= 0 ? '+' : ''}
              {power.aaTestResult.simulatedLiftPercent.toFixed(2)}%
            </div>
            <p className="mt-1 font-normal">
              False-positive rate: {power.aaTestResult.falsePositiveRatePercent.toFixed(1)}% (nominal \u03B1 = {power.aaTestResult.nominalAlphaPercent.toFixed(1)}%) —{' '}
              {power.aaTestResult.passed
                ? 'PASS — within tolerance, safe to launch.'
                : 'HARD STOP — false-positive rate exceeds tolerance. Launch is blocked until this is resolved.'}
            </p>
          </div>
        )}
      </div>

      {/* Empirical Simulation Backbone */}
      <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
        <div className="flex items-center gap-2">
          <AppIcon icon={FlaskConical} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">Empirical Power Simulation</p>
        </div>
        <p className="mt-1 text-xs text-text-secondary leading-relaxed">
          Replays 500-1,000 historical draws, applies a placebo treatment to each, and measures how often
          a lift of your target size would actually have been detected — an empirical check alongside the
          closed-form MDE formula above.
        </p>
        <button
          type="button"
          onClick={runEmpiricalPower}
          disabled={power.isRunningEmpiricalPower}
          className="focus-ring mt-3 flex items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {power.isRunningEmpiricalPower ? (
            <>
              <AppIcon icon={Loader2} size="xs" className="animate-spin" />
              Replaying historical draws…
            </>
          ) : (
            <>
              <AppIcon icon={Gauge} size="xs" />
              Run Empirical Power Simulation
            </>
          )}
        </button>
        {empiricalError && <p className="mt-1.5 text-micro text-red-600">{empiricalError}</p>}
        {power.empiricalPowerResult && !power.isRunningEmpiricalPower && (
          <div className="mt-2.5 rounded-xs bg-green-100 px-3 py-2 text-xs font-medium text-green-700">
            <AppIcon icon={CheckCircle2} size="sm" className="mr-1.5 inline" />
            Empirical power: {power.empiricalPowerResult.empiricalPowerPercent.toFixed(1)}% (based on{' '}
            {power.empiricalPowerResult.nDraws.toLocaleString()} historical draws with placebo treatment)
          </div>
        )}
      </div>
    </div>
  )
}
