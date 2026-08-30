import { TrendingUp } from 'lucide-react'
import type { WorkspaceStat } from '../context/types'
import { formatLiftLabel, type LiveExperimentStats } from './executiveStats'

/**
 * Metadata (label, sizing, icon, priority for responsive hiding) for each ticker stat.
 * The actual `value` is filled in at render time from live app data via
 * `buildWorkspaceStats` below — nothing here is a hardcoded placeholder number.
 */
const WORKSPACE_STAT_META: Omit<WorkspaceStat, 'value' | 'valueTone'>[] = [
  {
    id: 'total-experiments',
    label: 'Total Experiments',
    variant: 'highlight-blue',
    priority: 3,
    minWidth: 128,
  },
  {
    id: 'active-tests',
    label: 'Active Tests',
    variant: 'highlight-green',
    priority: 2,
    minWidth: 112,
  },
  {
    id: 'avg-performance',
    label: 'Avg. Performance',
    variant: 'metric',
    priority: 1,
    minWidth: 140,
    icon: TrendingUp,
  },
]

export function buildWorkspaceStats(liveStats: LiveExperimentStats): WorkspaceStat[] {
  const { totalExperiments, activeCount, avgLiftPercent } = liveStats
  const avgPositive = avgLiftPercent === null || avgLiftPercent >= 0

  const values: Record<string, { value: string; valueTone?: 'positive' | 'default' }> = {
    'total-experiments': { value: String(totalExperiments) },
    'active-tests': { value: String(activeCount) },
    'avg-performance': {
      value: formatLiftLabel(avgLiftPercent),
      valueTone: avgPositive ? 'positive' : 'default',
    },
  }

  return WORKSPACE_STAT_META.map((meta) => ({
    ...meta,
    ...values[meta.id],
  }))
}

const HIDE_PRIORITY_ORDER = [...WORKSPACE_STAT_META]
  .sort((a, b) => a.priority - b.priority)
  .map((s) => s.id)

const STAT_GAP = 6

export function getVisibleWorkspaceStats(stats: WorkspaceStat[], containerWidth: number): WorkspaceStat[] {
  if (containerWidth <= 0) return stats.slice(0, 1)

  let visible = [...stats]

  const measure = (list: WorkspaceStat[]) =>
    list.reduce((sum, stat, index) => sum + stat.minWidth + (index > 0 ? STAT_GAP : 0), 0)

  while (visible.length > 1 && measure(visible) > containerWidth) {
    const toRemove = HIDE_PRIORITY_ORDER.find((id) => visible.some((s) => s.id === id))
    if (!toRemove) break
    visible = visible.filter((s) => s.id !== toRemove)
  }

  return visible
}

