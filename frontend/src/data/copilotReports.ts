import { formatMessageTime } from './mock'
import { MODULE_BY_ID } from './moduleRegistry'
import { isChartArtifact, type ChartSpec, type ChatReport, type ModuleId, type UIArtifactCard } from '../context/types'

/**
 * Turns a finished Copilot turn into a Reports entry.
 *
 * Reports used to come only from Analytics Lab module runs, so a chat turn that
 * ran a real analysis or produced a chart left nothing on the Reports tab. A
 * turn earns a report when it produced an artifact — a chart or a computed stat
 * card. Prose alone does not: an answer with no tool behind it is a
 * conversation, and filing it as an analytical output would dilute the tab into
 * a chat log.
 */

/** Maps the tool the backend ran to the Analytics Lab module it corresponds to,
 * so a Copilot report files under the same type filter as the equivalent module
 * run. Mirrors `mapToolToModuleId` in MatchViewContext, which drives the lab
 * panel from the same tool names. */
function moduleForTool(toolName: string): ModuleId | null {
  const name = toolName.toLowerCase()
  if (name.includes('srm') || name.includes('health')) return 'health-monitor'
  if (name.includes('power') || name.includes('sample_size')) return 'power-calculator'
  if (name.includes('opportunity')) return 'opportunity-sizing'
  if (name.includes('metrics') || name.includes('guardrail')) return 'metrics-tracking'
  if (name.includes('sequential') || name.includes('sprt')) return 'sequential-testing'
  if (name.includes('diff_in_diff') || name.includes('causal')) return 'causal-did'
  if (name.includes('forecast') || name.includes('insights') || name.includes('monte_carlo')) {
    return 'forecasting'
  }
  if (name.includes('balance') || name.includes('allocation')) return 'balance-diagnostics'
  if (name.includes('planning') || name.includes('brief')) return 'brief-generator'
  if (name.includes('analysis') || name.includes('cuped') || name.includes('hypothesis_test')) {
    return 'experiment-analysis'
  }
  return null
}

/** The first tool that maps to a module. A turn often calls several; the module
 * of the first recognised one is the closest thing to "what this report is". */
function resolveModuleId(toolNames: string[]): ModuleId | null {
  for (const tool of toolNames) {
    const moduleId = moduleForTool(tool)
    if (moduleId) return moduleId
  }
  return null
}

function chartSpecOf(artifact: UIArtifactCard): ChartSpec | null {
  return isChartArtifact(artifact) ? (artifact.payload.chart_spec as ChartSpec) : null
}

/** Trims the prompt into a title, so the list reads as what was asked rather
 * than a row of identical "Copilot Analysis" headings. */
function titleFromPrompt(prompt: string, fallback: string): string {
  const cleaned = prompt.trim().replace(/\s+/g, ' ')
  if (!cleaned) return fallback
  const short = cleaned.length > 68 ? `${cleaned.slice(0, 67)}…` : cleaned
  return short.charAt(0).toUpperCase() + short.slice(1)
}

/**
 * The report body. The assistant's own answer is the best summary when it wrote
 * one; otherwise fall back to the artifact summaries the backend computed, so
 * the entry is never a blank card.
 */
function buildSummary(answerText: string, artifacts: UIArtifactCard[]): string {
  const answer = answerText.trim()
  if (answer) return answer

  const summaries = artifacts
    .map((a) => (typeof a.payload?.summary === 'string' ? a.payload.summary.trim() : ''))
    .filter(Boolean)
  if (summaries.length) return summaries.join('\n\n')

  return 'The Copilot produced the output below.'
}

export interface CopilotReportInput {
  artifacts: UIArtifactCard[]
  toolNames: string[]
  answerText: string
  prompt: string
  experiment: string
  threadId: string
}

export function buildCopilotReport({
  artifacts,
  toolNames,
  answerText,
  prompt,
  experiment,
  threadId,
}: CopilotReportInput): ChatReport | null {
  if (artifacts.length === 0) return null

  const moduleId = resolveModuleId(toolNames)
  const charts = artifacts.filter((a) => chartSpecOf(a) !== null)

  // Prefer the chart's own title — the backend names it after what it plots,
  // which beats echoing the prompt back at the reader.
  const chartTitle = charts.length === 1 ? chartSpecOf(charts[0])?.title : undefined
  const moduleLabel = moduleId ? MODULE_BY_ID[moduleId]?.label : undefined
  const title =
    chartTitle?.trim() ||
    (moduleLabel ? `${moduleLabel} — Copilot` : titleFromPrompt(prompt, 'Copilot Analysis'))

  const runId = `copilot_${Date.now()}`

  return {
    id: `report-${runId}`,
    runId,
    threadId,
    experiment,
    moduleId,
    title,
    summary: buildSummary(answerText, artifacts),
    artifacts,
    source: 'copilot',
    completedAt: formatMessageTime(),
    // Copilot turns are streamed, so there is no measured run duration to
    // report. An invented one would read as a real timing.
    duration: '—',
  }
}
