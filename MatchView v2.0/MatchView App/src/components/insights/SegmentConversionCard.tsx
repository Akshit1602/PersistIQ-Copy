import { CopilotButton } from './CopilotButton'

interface SegmentConversionCardProps {
  chartId?: string
  title?: string
}

const SEGMENTS = [
  { label: 'Mobile', value: 68 },
  { label: 'Desktop', value: 42 },
  { label: 'Returning', value: 82 },
  { label: 'New', value: 35 },
]

export function SegmentConversionCard({
  chartId = 'segment-conversion',
  title = 'Segment Conversion',
}: SegmentConversionCardProps) {
  return (
    <article className="relative min-h-[200px] glass-panel transition-all duration-instant hover:shadow-glow">
      <CopilotButton chartId={chartId} />
      <div className="p-5">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        <p className="mt-0.5 text-xs text-text-secondary">CVR by audience segment</p>
        <div className="mt-4 flex flex-col gap-3">
          {SEGMENTS.map((seg) => (
            <div key={seg.label} className="flex items-center gap-3">
              <span className="w-20 shrink-0 text-xs text-text-secondary">{seg.label}</span>
              <div className="h-2 min-w-0 flex-1 rounded-lg bg-surface-hover">
                <div
                  className="h-full rounded-lg bg-border-muted/50"
                  style={{ width: `${seg.value}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right text-xs tabular-nums text-text-primary">
                {seg.value}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </article>
  )
}
