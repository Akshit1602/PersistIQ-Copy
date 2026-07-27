import { Activity, CheckCircle2, TrendingUp } from 'lucide-react'
import type { WorkspaceStat } from '../context/types'

export const WORKSPACE_STATS: WorkspaceStat[] = [
  {
    id: 'total-experiments',
    label: 'Total Experiments',
    value: '247',
    variant: 'highlight-blue',
    priority: 5,
    minWidth: 128,
  },
  {
    id: 'active-tests',
    label: 'Active Tests',
    value: '34',
    variant: 'highlight-green',
    priority: 4,
    minWidth: 112,
  },
  {
    id: 'success-rate',
    label: 'Success Rate',
    value: '92.3%',
    variant: 'metric',
    priority: 3,
    minWidth: 118,
    icon: TrendingUp,
    valueTone: 'positive',
  },
  {
    id: 'avg-duration',
    label: 'Avg. Test Duration',
    value: '14 days',
    variant: 'metric',
    priority: 2,
    minWidth: 132,
    icon: Activity,
  },
  {
    id: 'completed-month',
    label: 'Completed This Month',
    value: '18',
    variant: 'metric',
    priority: 1,
    minWidth: 148,
    icon: CheckCircle2,
    iconTone: 'accent',
  },
]

const HIDE_PRIORITY_ORDER = [...WORKSPACE_STATS]
  .sort((a, b) => a.priority - b.priority)
  .map((s) => s.id)

const STAT_GAP = 6

export function getVisibleWorkspaceStats(containerWidth: number): WorkspaceStat[] {
  if (containerWidth <= 0) return WORKSPACE_STATS.slice(0, 1)

  let visible = [...WORKSPACE_STATS]

  const measure = (stats: WorkspaceStat[]) =>
    stats.reduce((sum, stat, index) => sum + stat.minWidth + (index > 0 ? STAT_GAP : 0), 0)

  while (visible.length > 1 && measure(visible) > containerWidth) {
    const toRemove = HIDE_PRIORITY_ORDER.find((id) => visible.some((s) => s.id === id))
    if (!toRemove) break
    visible = visible.filter((s) => s.id !== toRemove)
  }

  return visible
}
