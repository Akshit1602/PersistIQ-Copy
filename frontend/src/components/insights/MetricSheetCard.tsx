import { CopilotButton } from './CopilotButton'

interface MetricSheetCardProps {
  chartId?: string
  title?: string
}

const ROWS = [
  { metric: 'Treatment CVR', value: '12.8%', delta: '+4.2%' },
  { metric: 'Control CVR', value: '8.6%', delta: '—' },
  { metric: 'p-value', value: '0.003', delta: 'sig.' },
  { metric: 'Sample Size', value: '48,200', delta: '+2.1%' },
  { metric: 'SRM δ', value: '0.003', delta: 'OK' },
]

export function MetricSheetCard({
  chartId = 'metric-sheet',
  title = 'Raw Metric Sheet',
}: MetricSheetCardProps) {
  return (
    <article className="relative min-h-[200px] glass-panel transition-all duration-instant hover:shadow-glow">
      <CopilotButton chartId={chartId} />
      <div className="p-5">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        <p className="mt-0.5 text-xs text-text-secondary">Verified statistical outputs</p>
        <table className="mt-4 w-full text-xs">
          <thead>
            <tr className="border-b border-border-muted/15 text-left text-text-secondary">
              <th className="pb-2 font-medium">Metric</th>
              <th className="pb-2 font-medium">Value</th>
              <th className="pb-2 text-right font-medium">Delta</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.metric} className="border-b border-border-muted/10">
                <td className="py-2 text-text-secondary">{row.metric}</td>
                <td className="py-2 tabular-nums font-medium text-text-primary">{row.value}</td>
                <td className="py-2 text-right tabular-nums text-text-secondary">{row.delta}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  )
}
