import { DollarSign, CheckCircle2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import type { MoneyWaterfallResult } from '../../data/storeCausalRoi'
import { simulateDriverDecomposition } from '../../data/storeDriverDecomposition'
import { DriverDecompositionCard } from './DriverDecompositionCard'

interface Props {
  experimentKey: string
}

function formatMoney(v: number): string {
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  return `${sign}$${abs.toLocaleString()}`
}

export function RoiSynthesisWaterfallChart({ experimentKey }: Props) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const values = (moduleFormValuesByExperiment[experimentKey] ?? {}) as Record<string, Record<string, unknown>>
  const result = values['roi-synthesis']?.lastResult as MoneyWaterfallResult | undefined
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500

  if (!result) {
    return (
      <div className="rounded-[8px] border border-border-muted/20 bg-surface-hover/40 px-4 py-4 text-xs text-text-secondary">
        Run ROI Synthesis from the module panel to see the Money Waterfall bridge here.
      </div>
    )
  }

  const steps = [
    { label: 'Gross Incremental POS Revenue', value: result.grossIncrementalRevenue, isTotal: false },
    { label: '+ Cross-Category Halo Lift', value: result.crossCategoryHaloLift, isTotal: false },
    { label: '- Category Cannibalization', value: result.categoryCannibalization, isTotal: false },
    { label: '= Net Incremental Sales', value: result.netIncrementalSales, isTotal: true },
    { label: '- COGS', value: result.cogs, isTotal: false },
    { label: '- Store Operational Execution Cost', value: result.operationalExecutionCost, isTotal: false },
    { label: '= Final Net Incremental Margin', value: result.finalNetIncrementalMargin, isTotal: true },
  ]



  return (
    <div className="flex flex-col gap-3">
      <DriverDecompositionCard
        title="Final Causal Driver Tree"
        decomposition={simulateDriverDecomposition(testStoreCount, 2)}
      />

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <p className="type-overline mb-3">Money Waterfall Bridge</p>
        {(() => {
          // Compute the floating (running-total) start/end for each step —
          // total rows are grounded at 0 (they represent the actual
          // cumulative value at that point), non-total rows float between
          // the running total before and after they're applied.
          let running = 0
          const bars = steps.map((step) => {
            if (step.isTotal) {
              const bar = { ...step, barFrom: 0, barTo: step.value }
              running = step.value
              return bar
            }
            const from = running
            running += step.value
            return { ...step, barFrom: Math.min(from, running), barTo: Math.max(from, running) }
          })
          const allEdges = bars.flatMap((b) => [b.barFrom, b.barTo])
          const maxEdge = Math.max(...allEdges, 1)
          const minEdge = Math.min(...allEdges, 0)
          const edgeRange = Math.max(1, maxEdge - minEdge)

          const width = 560
          const height = 220
          const marginTop = 12
          const marginBottom = 46
          const marginLeft = 8
          const marginRight = 8
          const plotHeight = height - marginTop - marginBottom
          const plotWidth = width - marginLeft - marginRight
          const n = bars.length
          const gap = 10
          const barWidth = (plotWidth - gap * (n - 1)) / n

          const toY = (v: number) => marginTop + plotHeight - ((v - minEdge) / edgeRange) * plotHeight
          const barX = (i: number) => marginLeft + i * (barWidth + gap)

          return (
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }}>
              {/* Zero baseline */}
              <line x1={marginLeft} x2={width - marginRight} y1={toY(0)} y2={toY(0)} stroke="#E2E8F0" strokeWidth={1} />

              {bars.map((b, i) => {
                const x = barX(i)
                const yTop = toY(Math.max(b.barFrom, b.barTo))
                const yBottom = toY(Math.min(b.barFrom, b.barTo))
                const barHeight = Math.max(yBottom - yTop, 3)
                const isPositive = b.value >= 0
                const fill = b.isTotal ? '#2563EB' : isPositive ? '#22C55E' : '#EF4444'

                // Connector line: from the end of this bar to the start of the next
                const next = bars[i + 1]
                const connectorY = toY(b.barTo)

                return (
                  <g key={i}>
                    <rect x={x} y={yTop} width={barWidth} height={barHeight} fill={fill}>
                      <title>{`${b.label}: ${formatMoney(b.value)}`}</title>
                    </rect>
                    <text x={x + barWidth / 2} y={yTop - 6} textAnchor="middle" fontSize="10" fontWeight="600" fill={isPositive ? '#15803D' : '#B91C1C'}>
                      {formatMoney(b.value)}
                    </text>
                    <text x={x + barWidth / 2} y={height - marginBottom + 14} textAnchor="middle" fontSize="8.5" fill="#64748B">
                      {b.label.replace(/^[=+-]\s*/, '').split(' ').slice(0, 2).join(' ')}
                    </text>
                    <text x={x + barWidth / 2} y={height - marginBottom + 26} textAnchor="middle" fontSize="8.5" fill="#64748B">
                      {b.label.replace(/^[=+-]\s*/, '').split(' ').slice(2).join(' ')}
                    </text>
                    {next && (
                      <line
                        x1={x + barWidth}
                        x2={x + barWidth + gap}
                        y1={connectorY}
                        y2={connectorY}
                        stroke="#CBD5E1"
                        strokeWidth={1}
                        strokeDasharray="2,2"
                      />
                    )}
                  </g>
                )
              })}
            </svg>
          )
        })()}
      </div>

      <div className="rounded-[8px] border border-green-500/25 bg-green-50/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <AppIcon icon={DollarSign} size="sm" className="text-green-600" />
          <p className="text-sm font-semibold text-text-primary">Financial Audit Callout</p>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-3">
          <div>
            <p className="text-micro text-text-secondary">Realized iROAS</p>
            <p className="text-lg font-bold text-text-primary tabular-nums">{result.realizedIroas.toFixed(2)}x</p>
          </div>
          <div>
            <p className="text-micro text-text-secondary">Reconciliation</p>
            <p className="flex items-center gap-1 text-sm font-semibold text-green-700">
              <AppIcon icon={CheckCircle2} size="xs" />
              {result.reconciliationConfirmed ? 'Confirmed' : 'Pending'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
