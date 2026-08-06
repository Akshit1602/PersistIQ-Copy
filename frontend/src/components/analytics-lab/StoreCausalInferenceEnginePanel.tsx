import { useEffect, useRef, useState } from 'react'
import { GitBranch, Loader2, CheckCircle2, AlertTriangle, Activity, TrendingUp, BarChart3, Droplets } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import {
  type EstimatorEngine,
  type ConfounderToggles,
  type CausalInferenceResult,
  ESTIMATOR_ENGINE_OPTIONS,
  CONFOUNDER_TOGGLES_DEFAULTS,
  simulateCausalInference,
} from '../../data/storeCausalRoi'

const selectClass =
  'focus-ring box-border w-full min-w-0 appearance-none rounded-xs border border-border-muted/25 bg-surface-base bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat px-2.5 py-1.5 pr-8 text-xs text-text-primary'
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"

export function StoreCausalInferenceEnginePanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField, moduleRunStatus, labModuleId } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500

  const [estimator, setEstimator] = useState<EstimatorEngine>('sdid')
  const [confounders, setConfounders] = useState<ConfounderToggles>(CONFOUNDER_TOGGLES_DEFAULTS)
  const [result, setResult] = useState<CausalInferenceResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Auto-run simulation when a chat-triggered module run completes for causal-did
  const prevRunStatusRef = useRef<string>(moduleRunStatus)
  useEffect(() => {
    if (
      prevRunStatusRef.current === 'running' &&
      moduleRunStatus === 'success' &&
      labModuleId === 'causal-did' &&
      !isRunning
    ) {
      setIsRunning(true)
      setResult(null)
      simulateCausalInference(estimator, confounders, testStoreCount)
        .then((r) => {
          setResult(r)
          updateModuleFormField('causal-did' as any, 'lastResult', r)
        })
        .catch(() => setError('Auto-run failed — try running manually.'))
        .finally(() => setIsRunning(false))
    }
    prevRunStatusRef.current = moduleRunStatus
  }, [moduleRunStatus, labModuleId])

  const run = async () => {
    setError(null)
    setIsRunning(true)
    setResult(null)
    try {
      const r = await simulateCausalInference(estimator, confounders, testStoreCount)
      setResult(r)
      updateModuleFormField('causal-did' as any, 'lastResult', r)
    } catch {
      setError('Estimation failed to run — try again.')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <label className="type-overline mb-0.5 block">Estimator Engine</label>
          <p className="mb-1.5 text-micro text-text-secondary">
            Executes econometric model fitting to isolate true incremental store sales lift from ambient
            market noise.
          </p>
          <select
            className={selectClass}
            style={{ backgroundImage: selectChevronBg }}
            value={estimator}
            onChange={(e) => setEstimator(e.target.value as EstimatorEngine)}
          >
            {ESTIMATOR_ENGINE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <p className="mt-1 text-micro text-text-secondary">
            {ESTIMATOR_ENGINE_OPTIONS.find((o) => o.value === estimator)?.hint}
          </p>
        </div>

        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <p className="type-overline mb-1.5">Confounder Adjustment Toggles</p>
          <div className="flex flex-col gap-2">
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" className="h-3.5 w-3.5 accent-current" checked={confounders.weatherNormalization}
                onChange={(e) => setConfounders((c) => ({ ...c, weatherNormalization: e.target.checked }))} />
              <span className="text-xs text-text-primary">Weather Normalization Engine</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" className="h-3.5 w-3.5 accent-current" checked={confounders.stockoutVelocityMasking}
                onChange={(e) => setConfounders((c) => ({ ...c, stockoutVelocityMasking: e.target.checked }))} />
              <span className="text-xs text-text-primary">Stockout Velocity Collapse Masking</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" className="h-3.5 w-3.5 accent-current" checked={confounders.baselineVolumeDecileBalancing}
                onChange={(e) => setConfounders((c) => ({ ...c, baselineVolumeDecileBalancing: e.target.checked }))} />
              <span className="text-xs text-text-primary">Baseline Volume Decile Balancing</span>
            </label>
          </div>
          <p className="mt-2 rounded-xs border border-border-muted/15 bg-surface-hover/40 px-2.5 py-2 text-micro text-text-secondary leading-relaxed">
            Quarterly G.O.L.D. Tier is always included as a fixed covariate for DML and Synthetic Control
            estimators — it is not user-toggleable since matching quality depends on it.
          </p>
        </div>

        {error && <p className="text-micro text-red-600">{error}</p>}

        {result && !isRunning && (
          <>
          <div className={`rounded-[8px] border px-3 py-3 ${result.isSignificant ? 'border-green-500/30 bg-green-50/5' : 'border-amber-500/30 bg-amber-50/5'}`}>
            <div className="flex items-center gap-2 mb-2">
              <AppIcon icon={result.isSignificant ? CheckCircle2 : AlertTriangle} size="sm" className={result.isSignificant ? 'text-green-600' : 'text-amber-700'} />
              <p className="text-sm font-semibold text-text-primary">Net Incremental Lift: {result.netLiftPercent >= 0 ? '+' : ''}{result.netLiftPercent}%</p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-xs bg-surface-hover/40 px-2.5 py-2">
                <p className="text-micro text-text-secondary">Net Lift ($)</p>
                <p className="font-semibold text-text-primary tabular-nums">${result.netLiftDollars.toLocaleString()}</p>
              </div>
              <div className="rounded-xs bg-surface-hover/40 px-2.5 py-2">
                <p className="text-micro text-text-secondary">p-value</p>
                <p className="font-semibold text-text-primary tabular-nums">{result.pValue.toFixed(4)}</p>
              </div>
              <div className="col-span-2 rounded-xs bg-surface-hover/40 px-2.5 py-2">
                <p className="text-micro text-text-secondary">95% CI</p>
                <p className="font-semibold text-text-primary tabular-nums">[{result.ciLo}%, {result.ciHi}%]</p>
              </div>
            </div>
          </div>

          {/* ─── Diagnostic Metrics Bar ─── */}
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-muted/20 bg-surface-hover/40 px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
              <span className="text-micro font-medium text-text-secondary">Pre-Period MAPE</span>
              <span className="text-micro font-semibold text-text-primary tabular-nums">2.3%</span>
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-muted/20 bg-surface-hover/40 px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
              <span className="text-micro font-medium text-text-secondary">Parallel Trends P-Value</span>
              <span className="text-micro font-semibold text-text-primary tabular-nums">0.72</span>
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-muted/20 bg-surface-hover/40 px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
              <span className="text-micro font-medium text-text-secondary">iROAS</span>
              <span className="text-micro font-semibold text-text-primary tabular-nums">3.8x</span>
            </span>
          </div>

          {/* ─── Time-Series Counterfactual Chart ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <div className="flex items-center gap-2 mb-2">
              <AppIcon icon={Activity} size="sm" className="text-border-muted" />
              <p className="type-overline">Counterfactual Time-Series</p>
            </div>
            <p className="mb-2 text-micro text-text-secondary">Treatment Group (Actual) vs Synthetic Control (Counterfactual)</p>
            <div className="relative">
              <svg viewBox="0 0 400 140" className="w-full h-auto" preserveAspectRatio="xMidYMid meet">
                {/* Grid lines */}
                <line x1="40" y1="10" x2="40" y2="120" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
                <line x1="40" y1="120" x2="390" y2="120" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
                <line x1="40" y1="65" x2="390" y2="65" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
                <line x1="40" y1="35" x2="390" y2="35" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
                <line x1="40" y1="95" x2="390" y2="95" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
                {/* Intervention vertical dashed line */}
                <line x1="200" y1="10" x2="200" y2="120" stroke="#ef4444" strokeWidth="1" strokeDasharray="4,3" />
                <text x="202" y="18" fontSize="7" fill="#ef4444" fontWeight="500">Intervention</text>
                {/* Pre-intervention labels */}
                <text x="110" y="133" fontSize="6.5" fill="currentColor" className="text-text-secondary" textAnchor="middle">Pre-Period</text>
                <text x="295" y="133" fontSize="6.5" fill="currentColor" className="text-text-secondary" textAnchor="middle">Post-Period</text>
                {/* Synthetic Control (dashed gray) */}
                <polyline
                  fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4,2"
                  points="40,85 60,82 80,78 100,80 120,76 140,74 160,72 180,70 200,68 220,67 240,66 260,65 280,64 300,63 320,62 340,62 360,61 380,60"
                />
                {/* Treatment Actual (solid blue) */}
                <polyline
                  fill="none" stroke="#3b82f6" strokeWidth="1.8"
                  points="40,86 60,83 80,79 100,81 120,77 140,75 160,73 180,71 200,69 220,60 240,54 260,50 280,46 300,43 320,40 340,38 360,36 380,33"
                />
                {/* Lift shaded area between lines (post-intervention) */}
                <polygon
                  fill="#3b82f6" opacity="0.08"
                  points="200,69 220,60 240,54 260,50 280,46 300,43 320,40 340,38 360,36 380,33 380,60 360,61 340,62 320,62 300,63 280,64 260,65 240,66 220,67 200,68"
                />
                {/* Y-axis labels */}
                <text x="36" y="38" fontSize="6" fill="currentColor" className="text-text-secondary" textAnchor="end">$80K</text>
                <text x="36" y="68" fontSize="6" fill="currentColor" className="text-text-secondary" textAnchor="end">$60K</text>
                <text x="36" y="98" fontSize="6" fill="currentColor" className="text-text-secondary" textAnchor="end">$40K</text>
                <text x="36" y="122" fontSize="6" fill="currentColor" className="text-text-secondary" textAnchor="end">$20K</text>
              </svg>
              {/* Legend */}
              <div className="flex items-center gap-3 mt-1.5 px-1">
                <span className="flex items-center gap-1.5 text-micro text-text-secondary">
                  <span className="inline-block h-0.5 w-4 rounded bg-blue-500" /> Treatment (Actual)
                </span>
                <span className="flex items-center gap-1.5 text-micro text-text-secondary">
                  <span className="inline-block h-0.5 w-4 rounded border-t border-dashed border-slate-400" /> Synthetic Control
                </span>
              </div>
            </div>
          </div>

          {/* ─── Cumulative Lift Chart ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <div className="flex items-center gap-2 mb-2">
              <AppIcon icon={TrendingUp} size="sm" className="text-border-muted" />
              <p className="type-overline">Cumulative Incremental Lift</p>
            </div>
            <p className="mb-2 text-micro text-text-secondary">Daily incremental lift with 95% confidence interval band</p>
            <svg viewBox="0 0 400 120" className="w-full h-auto" preserveAspectRatio="xMidYMid meet">
              {/* Axes */}
              <line x1="40" y1="10" x2="40" y2="100" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
              <line x1="40" y1="100" x2="390" y2="100" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
              <line x1="40" y1="55" x2="390" y2="55" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
              {/* 95% CI shaded band */}
              <polygon
                fill="#10b981" opacity="0.12"
                points="40,75 70,72 100,68 130,62 160,58 190,52 220,47 250,43 280,40 310,37 340,35 370,33 390,32 390,88 370,85 340,82 310,80 280,78 250,76 220,74 190,72 160,71 130,73 100,77 70,80 40,83"
              />
              {/* Mean lift line */}
              <polyline
                fill="none" stroke="#10b981" strokeWidth="1.8"
                points="40,79 70,76 100,72 130,67 160,64 190,62 220,60 250,59 280,58 310,57 340,57 370,57 390,57"
              />
              {/* Zero baseline */}
              <line x1="40" y1="100" x2="390" y2="100" stroke="#94a3b8" strokeWidth="0.5" strokeDasharray="2,2" />
              {/* Labels */}
              <text x="36" y="57" fontSize="6" fill="currentColor" className="text-text-secondary" textAnchor="end">+{result.netLiftPercent}%</text>
              <text x="36" y="102" fontSize="6" fill="currentColor" className="text-text-secondary" textAnchor="end">0%</text>
              <text x="215" y="113" fontSize="6.5" fill="currentColor" className="text-text-secondary" textAnchor="middle">Weeks Post-Intervention</text>
            </svg>
            <div className="flex items-center gap-3 mt-1.5 px-1">
              <span className="flex items-center gap-1.5 text-micro text-text-secondary">
                <span className="inline-block h-0.5 w-4 rounded bg-emerald-500" /> Mean Lift
              </span>
              <span className="flex items-center gap-1.5 text-micro text-text-secondary">
                <span className="inline-block h-2.5 w-4 rounded bg-emerald-500/15" /> 95% CI Band
              </span>
            </div>
          </div>

          {/* ─── Synthetic Weights Panel ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <div className="flex items-center gap-2 mb-2">
              <AppIcon icon={BarChart3} size="sm" className="text-border-muted" />
              <p className="type-overline">Synthetic Control — Donor Weights</p>
            </div>
            <p className="mb-2.5 text-micro text-text-secondary">Top contributing stores/units and their weight in the synthetic control</p>
            <div className="flex flex-col gap-1.5">
              {[
                { store: 'ST-02841 (Dallas, TX)', weight: 18.2 },
                { store: 'ST-00417 (Phoenix, AZ)', weight: 14.7 },
                { store: 'ST-05109 (Charlotte, NC)', weight: 12.3 },
                { store: 'ST-01893 (Columbus, OH)', weight: 10.8 },
                { store: 'ST-07256 (Portland, OR)', weight: 9.1 },
                { store: 'ST-03648 (Tampa, FL)', weight: 7.6 },
                { store: 'ST-08912 (Denver, CO)', weight: 6.4 },
                { store: 'Others (38 stores)', weight: 20.9 },
              ].map((d) => (
                <div key={d.store} className="flex items-center gap-2">
                  <span className="w-[140px] shrink-0 truncate text-micro text-text-secondary" title={d.store}>{d.store}</span>
                  <div className="flex-1 h-3.5 rounded-full bg-surface-hover/60 overflow-hidden">
                    <div className="h-full rounded-full bg-blue-500/70" style={{ width: `${(d.weight / 21) * 100}%` }} />
                  </div>
                  <span className="w-[36px] shrink-0 text-right text-micro font-semibold tabular-nums text-text-primary">{d.weight}%</span>
                </div>
              ))}
            </div>
          </div>

          {/* ─── Confounder Bridge (Waterfall) ─── */}
          <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
            <div className="flex items-center gap-2 mb-2">
              <AppIcon icon={Droplets} size="sm" className="text-border-muted" />
              <p className="type-overline">Confounder Bridge — Lift Waterfall</p>
            </div>
            <p className="mb-2.5 text-micro text-text-secondary">How adjustments modify raw estimated lift to final net lift</p>
            <div className="flex flex-col gap-1">
              {[
                { label: 'Raw Estimated Lift', value: '+2.41%', delta: null, color: 'bg-blue-500', isFirst: true },
                { label: 'Weather Normalization', value: '-0.28%', delta: -0.28, color: 'bg-amber-500', isFirst: false },
                { label: 'Stockout Masking', value: '-0.22%', delta: -0.22, color: 'bg-amber-500', isFirst: false },
                { label: 'Volume Decile Balancing', value: '-0.16%', delta: -0.16, color: 'bg-amber-500', isFirst: false },
                { label: 'Net Lift (Final)', value: `+${result.netLiftPercent}%`, delta: null, color: 'bg-green-500', isFirst: false },
              ].map((step) => (
                <div key={step.label} className="flex items-center gap-2">
                  <span className="w-[150px] shrink-0 text-micro text-text-secondary">{step.label}</span>
                  <div className="flex-1 flex items-center h-5">
                    {step.delta === null ? (
                      <div className={`h-4 rounded-xs ${step.color}`} style={{ width: step.isFirst ? '80%' : '58%', opacity: step.isFirst ? 0.7 : 0.85 }} />
                    ) : (
                      <div className="flex items-center h-full" style={{ paddingLeft: '58%' }}>
                        <div className={`h-3.5 rounded-xs ${step.color}`} style={{ width: `${Math.abs(step.delta) * 35}%`, minWidth: '18px', opacity: 0.7 }} />
                      </div>
                    )}
                  </div>
                  <span className={`w-[46px] shrink-0 text-right text-micro font-semibold tabular-nums ${step.delta !== null ? 'text-amber-700' : step.isFirst ? 'text-blue-600' : 'text-green-600'}`}>{step.value}</span>
                </div>
              ))}
            </div>
          </div>
          </>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button type="button" onClick={run} disabled={isRunning}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
          {isRunning ? (<><AppIcon icon={Loader2} size="xs" className="animate-spin" /> Fitting {ESTIMATOR_ENGINE_OPTIONS.find(o=>o.value===estimator)?.label.split(' (')[0]}…</>) : (<><AppIcon icon={GitBranch} size="xs" /> Run Causal Inference Engine</>)}
        </button>
      </div>
    </div>
  )
}
