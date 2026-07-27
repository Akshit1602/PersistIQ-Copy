import type { ModuleId } from '../context/types'

export type WorkflowStepId =
  | 'opportunity-sizing'
  | 'metrics-tracking'
  | 'experiment-type'
  | 'power-calculator'
  | 'audience-selection'
  | 'brief-generator'

export interface WorkflowStep {
  id: WorkflowStepId
  label: string
  moduleId: ModuleId
}

/** Ordered pre-planning journey after Hypothesis Validator intake.
 * Audience remains a separate downstream step (wizard / Lab), not part of validator finalize. */
export const HYPOTHESIS_WORKFLOW_STEPS: WorkflowStep[] = [
  { id: 'opportunity-sizing', label: 'Opportunity Sizing', moduleId: 'opportunity-sizing' },
  { id: 'metrics-tracking', label: 'Metrics Approval', moduleId: 'metrics-tracking' },
  { id: 'experiment-type', label: 'Experiment Type', moduleId: 'experiment-type' },
  { id: 'power-calculator', label: 'Power Calculator', moduleId: 'power-calculator' },
  { id: 'audience-selection', label: 'Audience Selection', moduleId: 'audience-selection' },
  { id: 'brief-generator', label: 'Brief Generator', moduleId: 'brief-generator' },
]

export type WorkflowProgress = Partial<Record<WorkflowStepId, boolean>>

export function getWorkflowStepIndex(stepId: WorkflowStepId): number {
  return HYPOTHESIS_WORKFLOW_STEPS.findIndex((s) => s.id === stepId)
}

export function isWorkflowStepId(moduleId: string): moduleId is WorkflowStepId {
  return HYPOTHESIS_WORKFLOW_STEPS.some((s) => s.id === moduleId)
}

export function getNextIncompleteStep(
  progress: WorkflowProgress,
): WorkflowStep | null {
  return HYPOTHESIS_WORKFLOW_STEPS.find((s) => !progress[s.id]) ?? null
}

export function getNextStepAfter(stepId: WorkflowStepId): WorkflowStep | null {
  const idx = getWorkflowStepIndex(stepId)
  if (idx < 0 || idx >= HYPOTHESIS_WORKFLOW_STEPS.length - 1) return null
  return HYPOTHESIS_WORKFLOW_STEPS[idx + 1]
}

export function isStepComplete(progress: WorkflowProgress, stepId: WorkflowStepId): boolean {
  return Boolean(progress[stepId])
}

export function getRecommendedModuleId(progress: WorkflowProgress): ModuleId {
  return getNextIncompleteStep(progress)?.moduleId ?? 'brief-generator'
}

export function markStepComplete(
  progress: WorkflowProgress,
  stepId: WorkflowStepId,
): WorkflowProgress {
  return { ...progress, [stepId]: true }
}
