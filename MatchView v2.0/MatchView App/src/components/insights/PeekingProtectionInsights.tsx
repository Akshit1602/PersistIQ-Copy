import { ShieldAlert, CheckCircle2, TriangleAlert } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import type { PeekingProtectionResult } from '../../data/storeMonitoring'

interface Props {
  experimentKey: string
}

export function PeekingProtectionInsights({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['health-monitor']?.lastResult as PeekingProtectionResult | undefined

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run Peeking Protection & Futility from the module panel to see the confidence bounds here.
      </div>
    )
  }

  const scaleMin = -3
  const scaleMax = 3
  const span = scaleMax - scaleMin
  const toPct = (v: number) => Math.max(0, Math.min(100, ((v - scaleMin) / span) * 100))
  const zSigned = result.anytimeValidPValue < 0.5 ? result.currentZScore : -result.currentZScore
  const sigLowPct = toPct(-1.96)
  const sigHighPct = toPct(1.96)

  return (
    <div className="flex flex-col gap-3">
      {result.futilityTriggered && (
        <div className="flex items-start gap-2 rounded-[8px] border border-red-500/30 bg-red-50/40 px-4 py-3">
          <AppIcon icon={TriangleAlert} size="sm" className="mt-0.5 shrink-0 text-red-600" />
          <div>
            <p className="text-xs font-semibold text-red-700">Futility Alert — Early Termination Proposed</p>
            <p className="mt-0.5 text-micro text-red-700">
              Probability of clearing MDE has fallen to {result.probabilityOfClearingMde.toFixed(1)}% at week{' '}
              {result.currentWeek} — below the 5% futility threshold.
            </p>
          </div>
        </div>
      )}

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={ShieldAlert} size="sm" className="text-border-muted" />
          <p className="type-overline">In-Flight Statistical Bounds (mSPRT / BSTS anytime-valid)</p>
        </div>
        <div className="relative h-7 rounded-sm bg-surface-hover/60">
          <div className="absolute top-0 h-7 bg-green-100" style={{ left: `${sigLowPct}%`, width: `${sigHighPct - sigLowPct}%` }} />
          <div className="absolute top-0 h-7 w-px bg-border-muted/30" style={{ left: '50%' }} />
          <div
            className={`absolute top-0.5 h-6 w-1.5 rounded-full ${Math.abs(zSigned) > 1.96 ? 'bg-red-600' : 'bg-blue-600'}`}
            style={{ left: `calc(${toPct(zSigned)}% - 3px)` }}
            title={`z = ${zSigned.toFixed(2)}`}
          />
        </div>
        <div className="mt-1 flex justify-between text-micro text-text-secondary">
          <span>Non-significant zone</span>
          <span>|z| &gt; 1.96 = significant</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
          <p className="text-micro text-text-secondary">Anytime-Valid p-value</p>
          <p className="text-lg font-bold text-text-primary tabular-nums">{result.anytimeValidPValue.toFixed(3)}</p>
        </div>
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
          <p className="text-micro text-text-secondary">Probability of Clearing MDE</p>
          <p className={`text-lg font-bold tabular-nums ${result.probabilityOfClearingMde < 5 ? 'text-red-600' : 'text-green-600'}`}>
            {result.probabilityOfClearingMde.toFixed(1)}%
          </p>
        </div>
      </div>

      {!result.futilityTriggered && (
        <div className="flex items-center gap-1.5 rounded-[8px] bg-green-100 px-4 py-2.5 text-xs font-medium text-green-700">
          <AppIcon icon={CheckCircle2} size="xs" /> No futility concern — safe to continue.
        </div>
      )}
    </div>
  )
}
