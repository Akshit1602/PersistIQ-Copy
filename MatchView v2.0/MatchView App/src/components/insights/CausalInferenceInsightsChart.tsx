import { GitCompareArrows, CheckCircle2, AlertTriangle, Activity, TrendingUp, BarChart3, Droplets } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { ESTIMATOR_ENGINE_OPTIONS, type CausalInferenceResult } from '../../data/storeCausalRoi'

interface Props {
  experimentKey: string
}

export function CausalInferenceInsightsChart({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['causal-did']?.lastResult as CausalInferenceResult | undefined

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run the Causal Inference Engine from the module panel to see the estimated net lift and
        confidence interval here.
      </div>
    )
  }

  const estimatorLabel = ESTIMATOR_ENGINE_OPTIONS.find((o) => o.value === result.estimator)?.label ?? result.estimator

  const rangeMin = Math.min(0, result.ciLo) - 0.5
  const rangeMax = result.ciHi + 0.5
  const span = rangeMax - rangeMin
  const toPct = (v: number) => ((v - rangeMin) / span) * 100

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={GitCompareArrows} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">{estimatorLabel}</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-micro text-text-secondary">Net Lift (Estimated)</p>
            <p className={`text-lg font-bold tabular-nums ${result.netLiftPercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {result.netLiftPercent >= 0 ? '+' : ''}{result.netLiftPercent.toFixed(2)}%
            </p>
          </div>
          <div>
            <p className="text-micro text-text-secondary">Net Lift ($/year)</p>
            <p className="text-lg font-bold text-text-primary tabular-nums">${result.netLiftDollars.toLocaleString()}</p>
          </div>
        </div>
      </div>

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <p className="type-overline mb-2">95% Confidence Interval</p>
        <div className="relative h-8 rounded-sm bg-surface-hover/60">
          <div
            className="absolute top-0 h-8 rounded-sm bg-blue-200"
            style={{ left: `${toPct(result.ciLo)}%`, width: `${toPct(result.ciHi) - toPct(result.ciLo)}%` }}
          />
          <div className="absolute top-0 h-8 w-0.5 bg-blue-700" style={{ left: `${toPct(result.netLiftPercent)}%` }} />
          <div className="absolute top-0 h-8 w-px bg-border-muted/40" style={{ left: `${toPct(0)}%` }} />
        </div>
        <div className="mt-1 flex justify-between text-micro text-text-secondary">
          <span>{result.ciLo.toFixed(2)}%</span>
          <span>{result.ciHi.toFixed(2)}%</span>
        </div>
      </div>

      <div
        className={`flex items-center gap-2 rounded-[8px] px-4 py-2.5 text-xs font-medium ${
          result.isSignificant ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
        }`}
      >
        <AppIcon icon={result.isSignificant ? CheckCircle2 : AlertTriangle} size="sm" />
        {result.isSignificant
          ? `Statistically significant (p = ${result.pValue.toFixed(4)})`
          : `Not statistically significant (p = ${result.pValue.toFixed(4)})`}
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
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-4">
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={Activity} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">Counterfactual Time-Series</p>
        </div>
        <p className="mb-3 text-xs text-text-secondary">Treatment Group (Actual) vs Synthetic Control (Counterfactual)</p>
        <svg viewBox="0 0 520 160" className="w-full h-auto" preserveAspectRatio="xMidYMid meet">
          <line x1="50" y1="10" x2="50" y2="130" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
          <line x1="50" y1="130" x2="500" y2="130" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
          <line x1="50" y1="70" x2="500" y2="70" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
          <line x1="50" y1="40" x2="500" y2="40" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
          <line x1="50" y1="100" x2="500" y2="100" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
          <line x1="260" y1="10" x2="260" y2="130" stroke="#ef4444" strokeWidth="1" strokeDasharray="4,3" />
          <text x="263" y="20" fontSize="8" fill="#ef4444" fontWeight="500">Intervention</text>
          <text x="140" y="148" fontSize="7.5" fill="currentColor" className="text-text-secondary" textAnchor="middle">Pre-Period</text>
          <text x="380" y="148" fontSize="7.5" fill="currentColor" className="text-text-secondary" textAnchor="middle">Post-Period</text>
          <polyline fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4,2"
            points="50,95 80,92 110,88 140,90 170,86 200,84 230,82 260,78 290,77 320,76 350,75 380,74 410,73 440,72 470,71 500,70" />
          <polyline fill="none" stroke="#3b82f6" strokeWidth="2"
            points="50,96 80,93 110,89 140,91 170,87 200,85 230,83 260,79 290,68 320,60 350,54 380,48 410,43 440,39 470,36 500,32" />
          <polygon fill="#3b82f6" opacity="0.08"
            points="260,79 290,68 320,60 350,54 380,48 410,43 440,39 470,36 500,32 500,70 470,71 440,72 410,73 380,74 350,75 320,76 290,77 260,78" />
          <text x="46" y="43" fontSize="7" fill="currentColor" className="text-text-secondary" textAnchor="end">$80K</text>
          <text x="46" y="73" fontSize="7" fill="currentColor" className="text-text-secondary" textAnchor="end">$60K</text>
          <text x="46" y="103" fontSize="7" fill="currentColor" className="text-text-secondary" textAnchor="end">$40K</text>
          <text x="46" y="133" fontSize="7" fill="currentColor" className="text-text-secondary" textAnchor="end">$20K</text>
        </svg>
        <div className="flex items-center gap-4 mt-2">
          <span className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className="inline-block h-0.5 w-5 rounded bg-blue-500" /> Treatment (Actual)
          </span>
          <span className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className="inline-block h-0.5 w-5 rounded border-t border-dashed border-slate-400" /> Synthetic Control
          </span>
        </div>
      </div>

      {/* ─── Cumulative Lift Chart ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-4">
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={TrendingUp} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">Cumulative Incremental Lift</p>
        </div>
        <p className="mb-3 text-xs text-text-secondary">Daily incremental lift with 95% confidence interval band</p>
        <svg viewBox="0 0 520 130" className="w-full h-auto" preserveAspectRatio="xMidYMid meet">
          <line x1="50" y1="10" x2="50" y2="105" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
          <line x1="50" y1="105" x2="500" y2="105" stroke="currentColor" className="text-border-muted/20" strokeWidth="0.5" />
          <line x1="50" y1="57" x2="500" y2="57" stroke="currentColor" className="text-border-muted/10" strokeWidth="0.5" strokeDasharray="3,3" />
          <polygon fill="#10b981" opacity="0.12"
            points="50,80 90,77 130,72 170,66 210,60 250,55 290,50 330,46 370,43 410,40 450,38 490,36 500,35 500,92 490,90 450,87 410,85 370,83 330,81 290,79 250,77 210,75 170,74 130,78 90,82 50,86" />
          <polyline fill="none" stroke="#10b981" strokeWidth="2"
            points="50,83 90,79 130,75 170,70 210,67 250,65 290,63 330,62 370,61 410,60 450,60 490,60 500,60" />
          <text x="46" y="60" fontSize="7" fill="currentColor" className="text-text-secondary" textAnchor="end">+{result.netLiftPercent}%</text>
          <text x="46" y="108" fontSize="7" fill="currentColor" className="text-text-secondary" textAnchor="end">0%</text>
          <text x="275" y="120" fontSize="7.5" fill="currentColor" className="text-text-secondary" textAnchor="middle">Weeks Post-Intervention</text>
        </svg>
        <div className="flex items-center gap-4 mt-2">
          <span className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className="inline-block h-0.5 w-5 rounded bg-emerald-500" /> Mean Lift
          </span>
          <span className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className="inline-block h-3 w-5 rounded bg-emerald-500/15" /> 95% CI Band
          </span>
        </div>
      </div>

      {/* ─── Side-by-side: Synthetic Weights + Confounder Waterfall ─── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Synthetic Weights */}
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-4">
          <div className="flex items-center gap-2 mb-2">
            <AppIcon icon={BarChart3} size="sm" className="text-border-muted" />
            <p className="text-sm font-semibold text-text-primary">Synthetic Donor Weights</p>
          </div>
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
                <span className="w-[120px] shrink-0 truncate text-xs text-text-secondary" title={d.store}>{d.store}</span>
                <div className="flex-1 h-4 rounded-full bg-surface-hover/60 overflow-hidden">
                  <div className="h-full rounded-full bg-blue-500/70" style={{ width: `${(d.weight / 21) * 100}%` }} />
                </div>
                <span className="w-[38px] shrink-0 text-right text-xs font-semibold tabular-nums text-text-primary">{d.weight}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Confounder Bridge Waterfall */}
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-4">
          <div className="flex items-center gap-2 mb-2">
            <AppIcon icon={Droplets} size="sm" className="text-border-muted" />
            <p className="text-sm font-semibold text-text-primary">Confounder Bridge</p>
          </div>
          <div className="flex flex-col gap-1.5">
            {[
              { label: 'Raw Estimated Lift', value: '+2.41%', delta: null, color: 'bg-blue-500', isFirst: true },
              { label: 'Weather', value: '-0.28%', delta: -0.28, color: 'bg-amber-500', isFirst: false },
              { label: 'Stockout Masking', value: '-0.22%', delta: -0.22, color: 'bg-amber-500', isFirst: false },
              { label: 'Volume Decile', value: '-0.16%', delta: -0.16, color: 'bg-amber-500', isFirst: false },
              { label: 'Net Lift (Final)', value: `+${result.netLiftPercent}%`, delta: null, color: 'bg-green-500', isFirst: false },
            ].map((step) => (
              <div key={step.label} className="flex items-center gap-2">
                <span className="w-[120px] shrink-0 text-xs text-text-secondary">{step.label}</span>
                <div className="flex-1 flex items-center h-5">
                  {step.delta === null ? (
                    <div className={`h-4 rounded-xs ${step.color}`} style={{ width: step.isFirst ? '80%' : '58%', opacity: step.isFirst ? 0.7 : 0.85 }} />
                  ) : (
                    <div className="flex items-center h-full" style={{ paddingLeft: '58%' }}>
                      <div className={`h-3.5 rounded-xs ${step.color}`} style={{ width: `${Math.abs(step.delta) * 40}%`, minWidth: '20px', opacity: 0.7 }} />
                    </div>
                  )}
                </div>
                <span className={`w-[48px] shrink-0 text-right text-xs font-semibold tabular-nums ${step.delta !== null ? 'text-amber-700' : step.isFirst ? 'text-blue-600' : 'text-green-600'}`}>{step.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
