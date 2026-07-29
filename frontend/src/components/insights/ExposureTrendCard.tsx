import { CopilotButton } from './CopilotButton'

interface ExposureTrendCardProps {
  chartId?: string
  title?: string
}

export function ExposureTrendCard({
  chartId = 'exposure-trend',
  title = 'Daily Exposure Trend',
}: ExposureTrendCardProps) {
  const heights = [35, 42, 38, 55, 48, 62, 58, 70, 65, 78, 82, 75, 88, 92]

  return (
    <article className="relative min-h-[200px] glass-panel transition-all duration-instant hover:shadow-glow">
      <CopilotButton chartId={chartId} />
      <div className="p-5">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        <p className="mt-0.5 text-xs text-text-secondary">Treatment vs Control — 14 day window</p>
        <div className="mt-4 flex h-28 items-end gap-1">
          {heights.map((h, i) => (
            <div
              key={i}
              className="flex-1 rounded-t-xs bg-border-muted/30 transition-colors hover:bg-border-muted/60"
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
        <div className="mt-3 flex justify-between text-xs text-text-secondary">
          <span>Day 1</span>
          <span className="tabular-nums font-medium text-text-primary">2.4M impressions</span>
          <span>Day 14</span>
        </div>
      </div>
    </article>
  )
}
