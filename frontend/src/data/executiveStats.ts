import type { WorkflowProgressByExperiment } from '../context/types'
import { HYPOTHESIS_WORKFLOW_STEPS } from './hypothesisWorkflow'
import { PAST_EXPERIMENTS_DB } from './storeCausalRoi'

export interface LiveExperimentStats {
  totalExperiments: number
  activeCount: number
  completedCount: number
  avgLiftPercent: number | null
}

/**
 * Single source of truth for "how many experiments are running / done / lifting revenue"
 * across the app. Both the homepage Executive View card and the workspace header ticker
 * derive their numbers from this so they never disagree or show fabricated placeholder data.
 */
export function computeLiveExperimentStats(
  experiments: string[],
  workflowProgressByExperiment: WorkflowProgressByExperiment,
): LiveExperimentStats {
  const totalExperiments = experiments.length

  const completedCount = experiments.filter((name) => {
    const progress = workflowProgressByExperiment[name]
    if (!progress) return false
    return HYPOTHESIS_WORKFLOW_STEPS.every((step) => progress[step.id])
  }).length
  const activeCount = totalExperiments - completedCount

  const liftValues = PAST_EXPERIMENTS_DB.map((r) => r.netLiftPercent)
  const avgLiftPercent =
    liftValues.length > 0 ? liftValues.reduce((sum, v) => sum + v, 0) / liftValues.length : null

  return { totalExperiments, activeCount, completedCount, avgLiftPercent }
}

export function formatLiftLabel(avgLiftPercent: number | null): string {
  if (avgLiftPercent === null) return '—'
  return `${avgLiftPercent >= 0 ? '+' : ''}${avgLiftPercent.toFixed(1)}%`
}
