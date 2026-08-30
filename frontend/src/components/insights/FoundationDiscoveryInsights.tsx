import { Target } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import type { FoundationModuleKey } from '../../data/storeFoundationDiscovery'
import { FOUNDATION_MODULE_DATA } from '../../data/storeFoundationDiscovery'

interface Props {
  moduleKey: FoundationModuleKey
}

const STATUS_COLORS: Record<string, string> = {
  good: 'text-green-700 bg-green-100',
  warn: 'text-amber-700 bg-amber-100',
  bad: 'text-red-700 bg-red-100',
}

export function FoundationDiscoveryInsights({ moduleKey }: Props) {
  const data = FOUNDATION_MODULE_DATA[moduleKey]
  const chartValues = data.primaryChart.points.map((p) => p.value)
  const maxVal = Math.max(...chartValues, 1)
  const minVal = Math.min(0, ...chartValues)
  const range = Math.max(1, maxVal - minVal)

  const maxSegmentAbs = Math.max(...data.segmentBreakdown.segments.map((s) => Math.abs(s.value)), 1)

  return (
    <div className="flex flex-col gap-3">
      {/* Hypothesis Context Banner */}
      <div className="flex items-start gap-2 rounded-[8px] border border-blue-500/25 bg-blue-50/40 px-4 py-2.5">
        <AppIcon icon={Target} size="sm" className="mt-0.5 shrink-0 text-blue-600" />
        <p className="text-xs font-medium text-blue-800 leading-relaxed">{data.hypothesisContext}</p>
      </div>

      <p className="text-xs text-text-secondary leading-relaxed">{data.storeDefinition}</p>

      {/* Primary Chart (top, full width) */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <p className="type-overline mb-2">{data.primaryChart.title}</p>
        <div className="flex items-end gap-1.5" style={{ height: '110px' }}>
          {data.primaryChart.points.map((p) => {
            const barHeightPx = 6 + ((p.value - minVal) / range) * 84
            return (
              <div key={p.label} className="flex flex-1 flex-col items-center justify-end gap-1" style={{ height: '110px' }}>
                <div
                  className="w-full rounded-t-sm bg-blue-500"
                  style={{ height: `${Math.max(barHeightPx, 4)}px` }}
                  title={`${p.label}: ${p.value}${data.primaryChart.unit}`}
                />
                <span className="text-[9px] text-text-secondary">{p.label}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Bottom row: Segment Breakdown (left) + Metric Sheet (right) */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
          <p className="type-overline mb-2">{data.segmentBreakdown.title}</p>
          <div className="flex flex-col gap-2">
            {data.segmentBreakdown.segments.map((s) => {
              const widthPct = (Math.abs(s.value) / maxSegmentAbs) * 100
              return (
                <div key={s.label}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">{s.label}</span>
                    <span className={`font-semibold tabular-nums ${s.value < 0 ? 'text-red-600' : 'text-text-primary'}`}>
                      {s.value}{s.unit ?? ''}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-surface-hover">
                    <div
                      className={`h-1.5 rounded-full ${s.value < 0 ? 'bg-red-500' : 'bg-blue-500'}`}
                      style={{ width: `${Math.max(widthPct, 3)}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
          <p className="type-overline mb-2">{data.metricSheet.title}</p>
          <table className="w-full text-left text-xs">
            <tbody>
              {data.metricSheet.metrics.map((m) => (
                <tr key={m.label} className="border-t border-border-muted/10 first:border-t-0">
                  <td className="py-1.5 pr-2 text-text-secondary">{m.label}</td>
                  <td className="py-1.5 text-right">
                    <span className={`rounded-xs px-1.5 py-0.5 font-semibold ${m.status ? STATUS_COLORS[m.status] : 'text-text-primary'}`}>
                      {m.value}
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
