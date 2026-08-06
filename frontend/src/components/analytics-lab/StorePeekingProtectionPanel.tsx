import { useState } from 'react'
import { ShieldAlert, Loader2, CheckCircle2, TriangleAlert } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import { type PeekingProtectionResult, simulatePeekingProtection } from '../../data/storeMonitoring'

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary'

export function StorePeekingProtectionPanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500

  const [currentWeek, setCurrentWeek] = useState(3)
  const [result, setResult] = useState<PeekingProtectionResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setError(null)
    setIsRunning(true)
    setResult(null)
    try {
      const r = await simulatePeekingProtection(testStoreCount, currentWeek)
      setResult(r)
      updateModuleFormField('health-monitor' as any, 'lastResult', r)
    } catch {
      setError('Check failed to run — try again.')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <p className="type-overline mb-1">In-Flight Statistical Bounds</p>
          <p className="text-micro text-text-secondary leading-relaxed">
            Uses mSPRT / BSTS anytime-valid confidence sequences to allow safe weekly peeking without
            inflating false-positive rates.
          </p>
        </div>
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <p className="type-overline mb-1">Futility Alert Trigger</p>
          <p className="text-micro text-text-secondary leading-relaxed">
            Displays an early warning if the probability of clearing the Minimum Detectable Effect (MDE)
            falls below 5% after \u2265 2 weeks, proposing early termination for futile tests.
          </p>
        </div>

        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <label className="type-caption mb-0.5 block">Current Week of Flight</label>
          <input
            type="number"
            className={inputClass}
            value={currentWeek}
            min={1}
            max={52}
            onChange={(e) => setCurrentWeek(Number(e.target.value) || 1)}
          />
        </div>

        {error && <p className="text-micro text-red-600">{error}</p>}

        {result && !isRunning && (
          <>
            {result.futilityTriggered && (
              <div className="flex items-start gap-2 rounded-[8px] border border-red-500/30 bg-red-50/40 px-3 py-2.5">
                <AppIcon icon={TriangleAlert} size="sm" className="mt-0.5 shrink-0 text-red-600" />
                <div>
                  <p className="text-xs font-semibold text-red-700">Futility Alert — Early Termination Proposed</p>
                  <p className="mt-0.5 text-micro text-red-700">
                    Probability of clearing MDE has fallen to {result.probabilityOfClearingMde.toFixed(1)}% at
                    week {result.currentWeek} — below the 5% futility threshold.
                  </p>
                </div>
              </div>
            )}
            <div className="rounded-[8px] border border-border-muted/15 bg-surface-hover/40 px-3 py-3">
              <p className="type-caption mb-2">In-Flight Statistical Bounds (mSPRT / BSTS anytime-valid)</p>
              {(() => {
                const scaleMin = -3
                const scaleMax = 3
                const span = scaleMax - scaleMin
                const toPct = (v: number) => Math.max(0, Math.min(100, ((v - scaleMin) / span) * 100))
                const zSigned = result.anytimeValidPValue < 0.5 ? result.currentZScore : -result.currentZScore
                const sigLowPct = toPct(-1.96)
                const sigHighPct = toPct(1.96)
                return (
                  <div className="relative h-6 rounded-sm bg-surface-base">
                    <div className="absolute top-0 h-6 bg-green-100" style={{ left: `${sigLowPct}%`, width: `${sigHighPct - sigLowPct}%` }} />
                    <div className="absolute top-0 h-6 w-px bg-border-muted/30" style={{ left: '50%' }} />
                    <div
                      className={`absolute top-0.5 h-5 w-1.5 rounded-full ${Math.abs(zSigned) > 1.96 ? 'bg-red-600' : 'bg-blue-600'}`}
                      style={{ left: `calc(${toPct(zSigned)}% - 3px)` }}
                      title={`z = ${zSigned.toFixed(2)}`}
                    />
                  </div>
                )
              })()}
              <div className="mt-1 flex justify-between text-micro text-text-secondary">
                <span>Non-significant zone</span>
                <span>|z| &gt; 1.96 = significant</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <div className="rounded-[8px] border border-border-muted/15 bg-surface-hover/40 px-3 py-2.5">
                <p className="text-micro text-text-secondary">Anytime-Valid p-value</p>
                <p className="text-sm font-semibold text-text-primary tabular-nums">{result.anytimeValidPValue.toFixed(3)}</p>
              </div>
              <div className="rounded-[8px] border border-border-muted/15 bg-surface-hover/40 px-3 py-2.5">
                <p className="text-micro text-text-secondary">Current Z-Score</p>
                <p className="text-sm font-semibold text-text-primary tabular-nums">{result.currentZScore.toFixed(2)}</p>
              </div>
              <div className="col-span-2 rounded-[8px] border border-border-muted/15 bg-surface-hover/40 px-3 py-2.5">
                <p className="text-micro text-text-secondary">Probability of Clearing MDE</p>
                <p className={`text-sm font-semibold tabular-nums ${result.probabilityOfClearingMde < 5 ? 'text-red-600' : 'text-green-600'}`}>
                  {result.probabilityOfClearingMde.toFixed(1)}%
                </p>
              </div>
            </div>
            {!result.futilityTriggered && (
              <div className="flex items-center gap-1.5 rounded-[8px] bg-green-100 px-3 py-2 text-xs font-medium text-green-700">
                <AppIcon icon={CheckCircle2} size="xs" /> No futility concern — safe to continue.
              </div>
            )}
          </>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button
          type="button"
          onClick={run}
          disabled={isRunning}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isRunning ? (
            <>
              <AppIcon icon={Loader2} size="xs" className="animate-spin" />
              Checking statistical bounds…
            </>
          ) : (
            <>
              <AppIcon icon={ShieldAlert} size="xs" />
              Check Peeking Bounds & Futility
            </>
          )}
        </button>
      </div>
    </div>
  )
}
