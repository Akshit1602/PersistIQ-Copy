import type { ModuleId } from './types'

export type InterviewPhase = 'idle' | 'interviewing' | 'ready' | 'running' | 'complete'

export interface ActiveModuleContext {
  moduleId: ModuleId
  label: string
  startedAt: string
}

export interface InterviewPill {
  id: string
  label: string
  value: unknown
  fieldKey: string
}

export interface InterviewFieldStep {
  fieldKey: string
  question: string
  pills: InterviewPill[]
}

export interface ConversationalLoopState {
  activeModuleContext: ActiveModuleContext | null
  interviewPhase: InterviewPhase
  pendingFieldKey: string | null
  confirmedFieldKeys: string[]
  smartPills: InterviewPill[]
}

export interface ConversationalLoopActions {
  activateModuleContext: (moduleId: ModuleId) => void
  submitInterviewAnswer: (fieldKey: string, value: unknown, label?: string) => void
  executeSimulation: () => void
  pushResultsToInsights: () => void
}

export type ConversationalLoopContextValue = ConversationalLoopState & ConversationalLoopActions
