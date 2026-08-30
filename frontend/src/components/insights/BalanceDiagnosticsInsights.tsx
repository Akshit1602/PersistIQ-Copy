import { Scale, CheckCircle2, AlertTriangle } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import type { BalanceDiagnosticsRunResult } from '../../data/storeBalanceDiagnostics'

interface Props {
  experimentKey: string
}

export function BalanceDiagnosticsInsights({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['balance-diagnostics']?.lastResult as BalanceDiagnosticsRunResult | undefined

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run Balance Diagnostics from the module panel to see the Pre-Flight Audit Table here.
      </div>
    )
  }

  const rows = [
    result.rmspe && {
      label: 'Pre-Trend Parallelism (RMSPE)',
      score: result.rmspe.rmspe.toFixed(3),
      threshold: '< 0.05',
      passed: result.rmspe.passed,
    },
    result.covariateBalance && {
      label: 'Max |SMD| Score (incl. G.O.L.D. Tier)',
      score: result.covariateBalance.maxSmd.toFixed(3),
      threshold: '< 0.10',
      passed: result.covariateBalance.allBalanced,
    },
    result.placeboInTime && {
      label: 'Placebo-in-Time (A/A) False-Positive Rate',
      score: `${result.placeboInTime.falsePositiveRatePercent.toFixed(1)}%`,
      threshold: '< 7%',
      passed: result.placeboInTime.passed,
    },
  ].filter((r): r is { label: string; score: string; threshold: string; passed: boolean } => Boolean(r))

  return (
    <div className="flex flex-col gap-3">
      <div className={`rounded-[8px] border px-4 py-3 ${result.overallPassed ? 'border-green-500/30 bg-green-50/5' : 'border-red-500/30 bg-red-50/5'}`}>
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={Scale} size="sm" className={result.overallPassed ? 'text-green-600' : 'text-red-600'} />
          <p className="text-sm font-semibold text-text-primary">
            Pre-Flight Audit Table {result.overallPassed ? 'Complete \u2705' : 'Review Needed \u26A0\uFE0F'}
          </p>
        </div>
        <div className="overflow-hidden rounded-xs border border-border-muted/20">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-hover/60">
              <tr>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Diagnostic Test</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Score</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Threshold</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label} className="border-t border-border-muted/15">
                  <td className="px-2.5 py-1.5 text-text-primary">{row.label}</td>
                  <td className="px-2.5 py-1.5 tabular-nums">{row.score}</td>
                  <td className="px-2.5 py-1.5 text-text-secondary">{row.threshold}</td>
                  <td className="px-2.5 py-1.5">
                    <span className={`flex items-center gap-1 ${row.passed ? 'text-green-700' : 'text-red-700'}`}>
                      <AppIcon icon={row.passed ? CheckCircle2 : AlertTriangle} size="xs" />
                      {row.passed ? 'PASS' : 'REVIEW'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
