import { useEffect, useRef, useState } from 'react'
import { useMatchView } from '../../context/MatchViewContext'
import type { WorkspaceStat } from '../../context/types'
import { getVisibleWorkspaceStats } from '../../data/workspaceStats'
import { AppIcon } from '../shared/AppIcon'

function HighlightStat({ stat }: { stat: WorkspaceStat }) {
  const isBlue = stat.variant === 'highlight-blue'
  return (
    <div
      className={`flex shrink-0 items-center gap-2 rounded-xs border px-2.5 py-1 ${
        isBlue
          ? 'border-blue-500/20 bg-blue-500/8'
          : 'border-emerald-500/20 bg-emerald-500/8'
      }`}
      title={`${stat.label}: ${stat.value}`}
    >
      <span
        className={`text-sm font-bold tabular-nums leading-none ${
          isBlue ? 'text-blue-600' : 'text-emerald-600'
        }`}
      >
        {stat.value}
      </span>
      <span className="hidden text-micro text-text-secondary sm:inline">{stat.label}</span>
    </div>
  )
}

function MetricStat({ stat }: { stat: WorkspaceStat }) {
  const Icon = stat.icon
  const valueClass =
    stat.valueTone === 'positive' ? 'text-emerald-600' : 'text-text-primary'
  const iconClass =
    stat.iconTone === 'accent' ? 'text-violet-500' : 'text-blue-500'

  return (
    <div
      className="flex shrink-0 items-center gap-1.5 rounded-xs border border-border-muted/15 bg-surface-base px-2 py-1"
      title={`${stat.label}: ${stat.value}`}
    >
      {Icon && <AppIcon icon={Icon} size="xs" className={iconClass} />}
      <span className="hidden text-micro text-text-secondary md:inline">{stat.label}</span>
      <span className={`text-xs font-semibold tabular-nums ${valueClass}`}>{stat.value}</span>
    </div>
  )
}

function StatChip({ stat }: { stat: WorkspaceStat }) {
  if (stat.variant === 'highlight-blue' || stat.variant === 'highlight-green') {
    return <HighlightStat stat={stat} />
  }
  return <MetricStat stat={stat} />
}

export function CriticalInsightsTicker() {
  const { tickerMetrics } = useMatchView()
  const containerRef = useRef<HTMLDivElement>(null)
  const [visibleStats, setVisibleStats] = useState<WorkspaceStat[]>(tickerMetrics)

  useEffect(() => {
    const node = containerRef.current
    if (!node) return

    const update = () => {
      setVisibleStats(getVisibleWorkspaceStats(node.clientWidth))
    }

    update()
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [tickerMetrics])

  return (
    <div
      ref={containerRef}
      className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden"
      aria-label="Workspace statistics"
    >
      {visibleStats.map((stat) => (
        <StatChip key={stat.id} stat={stat} />
      ))}
    </div>
  )
}
