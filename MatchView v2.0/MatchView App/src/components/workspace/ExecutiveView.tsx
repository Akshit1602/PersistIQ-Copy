import { useMemo } from 'react'
import { ArrowDownRight, ArrowUpRight, LayoutDashboard } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { computeLiveExperimentStats, formatLiftLabel } from '../../data/executiveStats'
import { AppIcon } from '../shared/AppIcon'

interface ExecutiveStat {
  id: string
  value: string
  label: string
  sublabel: string
  valueClassName: string
  trend?: 'up' | 'down'
}

export function ExecutiveView() {
  const { experiments, workflowProgressByExperiment } = useMatchView()

  const stats = useMemo<ExecutiveStat[]>(() => {
    const { totalExperiments, activeCount, completedCount, avgLiftPercent } =
      computeLiveExperimentStats(experiments, workflowProgressByExperiment)

    const avgPositive = avgLiftPercent === null || avgLiftPercent >= 0
    const avgLabel = formatLiftLabel(avgLiftPercent)

    return [
      {
        id: 'total-experiments',
        value: String(totalExperiments),
        label: 'Total Experiments',
        sublabel: 'All Categories',
        valueClassName: 'text-blue-600',
      },
      {
        id: 'currently-active',
        value: String(activeCount),
        label: 'Currently Active',
        sublabel: 'Running Tests',
        valueClassName: 'text-emerald-600',
      },
      {
        id: 'completed',
        value: String(completedCount),
        label: 'Completed',
        sublabel: 'Successful Tests',
        valueClassName: 'text-violet-600',
      },
      {
        id: 'avg-performance',
        value: avgLabel,
        label: 'Avg. Performance',
        sublabel: 'Revenue Impact',
        valueClassName:
          avgLiftPercent === null ? 'text-text-secondary' : avgPositive ? 'text-emerald-600' : 'text-red-600',
        trend: avgLiftPercent === null ? undefined : avgPositive ? 'up' : 'down',
      },
    ]
  }, [experiments, workflowProgressByExperiment])

  return (
    <section
      aria-label="Executive View"
      className="glass-panel rounded-[8px] border border-border-muted/15 p-4"
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-xs bg-surface-hover text-border-muted">
          <AppIcon icon={LayoutDashboard} size="sm" />
        </span>
        <h2 className="text-sm font-semibold text-text-primary">Executive View</h2>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.id}
            className="rounded-[8px] border border-border-muted/15 bg-surface-base px-4 py-3"
          >
            <p
              className={`flex items-baseline gap-1 text-2xl font-bold tabular-nums leading-none ${stat.valueClassName}`}
            >
              {stat.value}
              {stat.trend === 'up' ? (
                <AppIcon icon={ArrowUpRight} size="xs" className="text-emerald-600" />
              ) : stat.trend === 'down' ? (
                <AppIcon icon={ArrowDownRight} size="xs" className="text-red-600" />
              ) : null}
            </p>
            <p className="mt-2 text-xs font-semibold text-text-primary">{stat.label}</p>
            <p className="mt-0.5 text-micro text-text-secondary">{stat.sublabel}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
