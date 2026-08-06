import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import type { SimpsonsParadoxResult } from '../../data/storeCausalRoi'

interface Props {
  experimentKey: string
}

const DIMENSION_LABELS: Record<string, string> = {
  format: 'Store Format',
  size: 'Store Size Tier',
  climate: 'Climate Zone',
  gold_tier: 'Quarterly G.O.L.D. Tier',
}

export function SimpsonsParadoxInsightsChart({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['simpsons-paradox']?.lastResult as SimpsonsParadoxResult | undefined

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run the Simpson's Paradox & Heterogeneity Checker from the module panel to see subgroup lift here.
      </div>
    )
  }

  const maxAbs = Math.max(...result.subgroups.map((s) => Math.abs(s.liftPercent)), Math.abs(result.overallLiftPercent), 1)
  const dimensions = ['format', 'size', 'climate', 'gold_tier'] as const

  return (
    <div className="flex flex-col gap-3">
      {result.paradoxDetected && (
        <div className="flex items-start gap-2 rounded-[8px] border border-red-500/30 bg-red-50/40 px-4 py-3">
          <AppIcon icon={AlertTriangle} size="sm" className="mt-0.5 shrink-0 text-red-600" />
          <div>
            <p className="text-xs font-semibold text-red-700">SIMPSON'S PARADOX DETECTED</p>
            <p className="mt-0.5 text-micro text-red-700 leading-relaxed">
              Overall chain lift is positive (+{result.overallLiftPercent.toFixed(1)}%), but negative across{' '}
              {result.paradoxSegment} — recommend a targeted rollout rather than fleet-wide expansion.
            </p>
          </div>
        </div>
      )}
      {!result.paradoxDetected && (
        <div className="flex items-center gap-2 rounded-[8px] bg-green-100 px-4 py-2.5 text-xs font-medium text-green-700">
          <AppIcon icon={CheckCircle2} size="sm" /> No aggregate-trap paradox detected across subgroups.
        </div>
      )}

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <p className="type-overline mb-1">Overall Chain Lift</p>
        <p className={`text-xl font-bold tabular-nums ${result.overallLiftPercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
          {result.overallLiftPercent >= 0 ? '+' : ''}{result.overallLiftPercent.toFixed(2)}%
        </p>
      </div>

      {dimensions.map((dim) => {
        const segs = result.subgroups.filter((s) => s.dimension === dim)
        return (
          <div key={dim} className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
            <p className="type-overline mb-2">{DIMENSION_LABELS[dim]}</p>
            <div className="flex flex-col gap-1.5">
              {segs.map((s) => {
                const barWidthPct = (Math.abs(s.liftPercent) / maxAbs) * 100
                return (
                  <div key={s.segment} className="flex items-center gap-2">
                    <span className="w-20 shrink-0 text-xs text-text-secondary">{s.segment}</span>
                    <div className="h-4 flex-1 rounded-sm bg-surface-hover/60">
                      <div
                        className={`h-4 rounded-sm ${s.liftPercent >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                        style={{ width: `${Math.max(barWidthPct, 3)}%` }}
                      />
                    </div>
                    <span className={`w-16 shrink-0 text-right text-xs font-semibold tabular-nums ${s.liftPercent >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                      {s.liftPercent >= 0 ? '+' : ''}{s.liftPercent.toFixed(1)}%
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
