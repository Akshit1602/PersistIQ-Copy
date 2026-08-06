import { buildModuleEvaluation } from './moduleEvaluation'
import { MODULE_BY_ID } from './moduleRegistry'
import { INITIAL_MODULE_RUNS } from './initialModuleRuns'
import type { ChatReport } from '../context/types'

export function buildInitialReports(): ChatReport[] {
  const reports: ChatReport[] = []

  for (const [experiment, runs] of Object.entries(INITIAL_MODULE_RUNS)) {
    for (const run of runs) {
      const mod = MODULE_BY_ID[run.moduleId]
      const evaluation = buildModuleEvaluation(run.moduleId, run.params)
      reports.push({
        id: `report-${run.id}`,
        runId: run.id,
        threadId: 't1',
        experiment,
        moduleId: run.moduleId,
        title: `${mod.label} Report`,
        summary: evaluation.summary,
        evaluation,
        completedAt: run.completedAt,
        duration: run.duration,
      })
    }
  }

  return reports
}
