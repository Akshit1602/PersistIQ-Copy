import type { ModuleId } from '../context/types'
import { MODULE_BY_ID } from './moduleRegistry'

export interface ExecutionLogStep {
  line: string
  delayMs: number
}

export function buildExecutionLogStream(
  moduleId: ModuleId,
  params: Record<string, unknown>,
  experiment: string,
): ExecutionLogStep[] {
  const mod = MODULE_BY_ID[moduleId]
  const paramSummary = Object.entries(params)
    .filter(([k]) => !['moduleLabel', 'experimentScope'].includes(k))
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ')

  return [
    { line: `[INFO]  pipeline.init — Experiment "${experiment}" loaded`, delayMs: 0 },
    { line: `[INFO]  ${mod.id} — Initializing ${mod.label} Model…`, delayMs: 200 },
    { line: `[DEBUG] config.validate — Params: { ${paramSummary || 'defaults'} }`, delayMs: 500 },
    { line: `[INFO]  schema.validate — Source tables verified`, delayMs: 800 },
    {
      line: `[SQL]   SELECT * FROM exp_results WHERE exp_id = '${experiment.replace(/\s/g, '_').toLowerCase()}'`,
      delayMs: 1100,
    },
    { line: `[WARN]  srm.check — Minor allocation drift detected (δ=0.003)`, delayMs: 1400 },
    {
      line: `[INFO]  ${mod.id} — ${mod.label} ran successfully in ${mod.mockDuration}`,
      delayMs: 1700,
    },
    { line: `[DEBUG] cache.refresh — Insights snapshot updated for ${mod.label}`, delayMs: 1900 },
  ]
}
