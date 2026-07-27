import type { ChartData } from '../../data/mock'
import { CopilotButton } from './CopilotButton'

interface ChartCardProps {
  chart: ChartData
  featured?: boolean
}

export function ChartCard({ chart, featured = false }: ChartCardProps) {
  return (
    <article
      className={`relative min-h-[200px] glass-panel transition-all duration-instant hover:shadow-glow ${
        featured ? 'col-span-2' : ''
      }`}
    >
      <CopilotButton chartId={chart.id} />

      <div className="p-5">
        <h3 className="text-sm font-semibold text-text-primary">{chart.title}</h3>
        <p className="mt-0.5 text-xs text-text-secondary">{chart.subtitle}</p>

        <div className="mt-4 flex items-end justify-between">
          <span
            className={`tabular-nums text-3xl font-bold ${
              chart.positive ? 'text-text-primary' : 'text-text-secondary'
            }`}
          >
            {chart.metric}
          </span>
          <span className="text-xs text-text-secondary">{chart.change}</span>
        </div>

        <div className="mt-4 flex h-24 items-end gap-1">
          {[40, 55, 45, 60, 52, 68, 72, 65, 78, 82, 75, 88, 85, 92].map((h, i) => (
            <div
              key={i}
              className="flex-1 rounded-t-xs bg-border-muted/30 transition-colors hover:bg-border-muted/60"
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
      </div>
    </article>
  )
}
