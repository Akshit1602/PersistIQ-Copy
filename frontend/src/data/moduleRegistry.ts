import type { ModuleId, Persona, Phase, WorkspaceStat } from '../context/types'
import { WORKSPACE_STATS } from './workspaceStats'

export type ModulePhaseId = 'foundation' | 'preplanning' | 'monitoring' | 'causal'

export interface ModuleDefinition {
  id: ModuleId
  label: string
  phaseId: ModulePhaseId
  phaseLabel: string
  executivePhase: Phase
  mockDuration: string
}

export interface ModulePhaseGroup {
  id: ModulePhaseId
  label: string
  modules: ModuleDefinition[]
}

export interface PhaseOption {
  value: Phase
  label: string
  children?: PhaseOption[]
}

export interface ActionPill {
  id: string
  label: string
  prompt: string
}

export const MODULE_LIST: ModuleDefinition[] = [
  { id: 'data-validation', label: 'Data Validation', phaseId: 'foundation', phaseLabel: 'Foundation & Discovery', executivePhase: 'discovery', mockDuration: '2.14s' },
  { id: 'dimension-setup', label: 'Dimension Setup', phaseId: 'foundation', phaseLabel: 'Foundation & Discovery', executivePhase: 'discovery', mockDuration: '1.87s' },
  { id: 'distribution-shift', label: 'Distribution Shift', phaseId: 'foundation', phaseLabel: 'Foundation & Discovery', executivePhase: 'discovery', mockDuration: '3.22s' },
  { id: 'pipeline-health', label: 'Pipeline Health', phaseId: 'foundation', phaseLabel: 'Foundation & Discovery', executivePhase: 'discovery', mockDuration: '1.45s' },
  { id: 'schema-discovery', label: 'Schema Discovery', phaseId: 'foundation', phaseLabel: 'Foundation & Discovery', executivePhase: 'discovery', mockDuration: '2.91s' },
  { id: 'watchtower', label: 'Watchtower', phaseId: 'foundation', phaseLabel: 'Foundation & Discovery', executivePhase: 'discovery', mockDuration: '0.98s' },
  { id: 'opportunity-sizing', label: 'Opportunity Sizing', phaseId: 'preplanning', phaseLabel: 'Pre-Planning & Specs', executivePhase: 'planning', mockDuration: '4.56s' },
  { id: 'metrics-tracking', label: 'Metrics Tracking', phaseId: 'preplanning', phaseLabel: 'Pre-Planning & Specs', executivePhase: 'planning', mockDuration: '1.76s' },
  { id: 'experiment-type', label: 'Experiment Type', phaseId: 'preplanning', phaseLabel: 'Pre-Planning & Specs', executivePhase: 'planning', mockDuration: '1.20s' },
  { id: 'power-calculator', label: 'Power Calculator', phaseId: 'preplanning', phaseLabel: 'Pre-Planning & Specs', executivePhase: 'planning', mockDuration: '3.88s' },
  { id: 'audience-selection', label: 'Audience Selection', phaseId: 'preplanning', phaseLabel: 'Pre-Planning & Specs', executivePhase: 'planning', mockDuration: '3.10s' },
  { id: 'balance-diagnostics', label: 'Balance Diagnostics', phaseId: 'preplanning', phaseLabel: 'Pre-Planning & Specs', executivePhase: 'planning', mockDuration: '2.67s' },
  { id: 'brief-generator', label: 'Brief Generator', phaseId: 'preplanning', phaseLabel: 'Pre-Planning & Specs', executivePhase: 'planning', mockDuration: '4.12s' },
  { id: 'experiment-analysis', label: 'Experiment Analysis', phaseId: 'monitoring', phaseLabel: 'Live Execution Monitoring', executivePhase: 'monitoring', mockDuration: '2.34s' },
  { id: 'health-monitor', label: 'Health Monitor', phaseId: 'monitoring', phaseLabel: 'Live Execution Monitoring', executivePhase: 'monitoring', mockDuration: '1.12s' },
  { id: 'sequential-testing', label: 'Sequential Testing', phaseId: 'monitoring', phaseLabel: 'Live Execution Monitoring', executivePhase: 'monitoring', mockDuration: '5.01s' },
  { id: 'causal-did', label: 'Causal Inference (DiD)', phaseId: 'causal', phaseLabel: 'Causal Inference & ROI', executivePhase: 'analysis', mockDuration: '6.23s' },
  { id: 'forecasting', label: 'Forecasting', phaseId: 'causal', phaseLabel: 'Causal Inference & ROI', executivePhase: 'analysis', mockDuration: '3.45s' },
  { id: 'learnings-repository', label: 'Learnings Repository', phaseId: 'causal', phaseLabel: 'Causal Inference & ROI', executivePhase: 'analysis', mockDuration: '1.89s' },
  { id: 'roi-synthesis', label: 'ROI Synthesis', phaseId: 'causal', phaseLabel: 'Causal Inference & ROI', executivePhase: 'analysis', mockDuration: '2.78s' },
  { id: 'simpsons-paradox', label: "Simpson's Paradox Checker", phaseId: 'causal', phaseLabel: 'Causal Inference & ROI', executivePhase: 'analysis', mockDuration: '3.67s' },
]

export const MODULE_BY_ID = Object.fromEntries(
  MODULE_LIST.map((m) => [m.id, m]),
) as Record<ModuleId, ModuleDefinition>

export const ALL_MODULE_IDS = MODULE_LIST.map((m) => m.id)

export const MODULE_PHASES: ModulePhaseGroup[] = [
  {
    id: 'foundation',
    label: 'Foundation & Discovery',
    modules: MODULE_LIST.filter((m) => m.phaseId === 'foundation'),
  },
  {
    id: 'preplanning',
    label: 'Pre-Planning & Specs',
    modules: MODULE_LIST.filter((m) => m.phaseId === 'preplanning'),
  },
  {
    id: 'monitoring',
    label: 'Live Execution Monitoring',
    modules: MODULE_LIST.filter((m) => m.phaseId === 'monitoring'),
  },
  {
    id: 'causal',
    label: 'Causal Inference & ROI',
    modules: MODULE_LIST.filter((m) => m.phaseId === 'causal'),
  },
]

export const EXECUTIVE_PHASES: PhaseOption[] = [
  { value: 'auto', label: 'Auto-Detect' },
  { value: 'discovery', label: 'Discovery' },
  { value: 'planning', label: 'Planning' },
  { value: 'monitoring', label: 'Monitoring' },
  { value: 'analysis', label: 'Analysis' },
]

export function buildAnalystPhaseOptions(): PhaseOption[] {
  return [
    { value: 'auto', label: 'Auto-Detect' },
    ...MODULE_PHASES.map((group) => ({
      value: group.id as Phase,
      label: group.label,
      children: group.modules.map((m) => ({
        value: m.id as Phase,
        label: m.label,
      })),
    })),
  ]
}

export const PHASE_LABELS: Record<string, string> = {
  auto: 'Auto-Detect',
  discovery: 'Discovery',
  planning: 'Planning',
  monitoring: 'Monitoring',
  analysis: 'Analysis',
  foundation: 'Foundation & Discovery',
  preplanning: 'Pre-Planning & Specs',
  causal: 'Causal Inference & ROI',
  ...Object.fromEntries(MODULE_LIST.map((m) => [m.id, m.label])),
}

const EXECUTIVE_PILLS: Partial<Record<Phase, ActionPill[]>> = {
  auto: [
    { id: 'e-auto-1', label: 'Summarize Results', prompt: 'Summarize the latest experiment results in business terms.' },
    { id: 'e-auto-2', label: 'Key Takeaways', prompt: 'What are the top 3 business takeaways from this experiment?' },
  ],
  discovery: [
    { id: 'e-disc-1', label: 'Market Overview', prompt: 'Give me a high-level market overview for this experiment.' },
    { id: 'e-disc-2', label: 'Audience Insights', prompt: 'What audience segments should we prioritize?' },
  ],
  planning: [
    { id: 'e-plan-1', label: 'Size Opportunity', prompt: 'Run opportunity sizing for this digital hypothesis.' },
    { id: 'e-plan-2', label: 'Draft Brief', prompt: 'Draft a marketing brief for this experiment.' },
  ],
  monitoring: [
    { id: 'e-mon-1', label: 'Health Check', prompt: 'Is the experiment running smoothly? Any concerns?' },
    { id: 'e-mon-2', label: 'Progress Update', prompt: 'Give me a progress update on current KPIs.' },
  ],
  analysis: [
    { id: 'e-ana-1', label: 'ROI Summary', prompt: 'What is the projected ROI from this experiment?' },
    { id: 'e-ana-2', label: 'Lift Report', prompt: 'Summarize lift and reach metrics for leadership.' },
  ],
}

const ANALYST_BUCKET_PILLS: Partial<Record<Phase, ActionPill[]>> = {
  auto: [
    { id: 'a-auto-1', label: 'Size Opportunity', prompt: 'Run opportunity sizing to validate this hypothesis.' },
    { id: 'a-auto-2', label: 'Metrics Tracking', prompt: 'Define feature description and experiment maturity for metrics tracking.' },
  ],
  discovery: [
    { id: 'a-disc-1', label: 'Schema Discovery', prompt: 'Discover and map all relevant data schemas.' },
    { id: 'a-disc-2', label: 'Data Validation', prompt: 'Run data validation checks on input datasets.' },
  ],
  planning: [
    { id: 'a-plan-1', label: 'Size Opportunity', prompt: 'Calculate addressable opportunity size for this digital hypothesis.' },
    { id: 'a-plan-2', label: 'Metrics Tracking', prompt: 'Set feature description and experiment maturity (mvp, iteration, or critical).' },
  ],
  monitoring: [
    { id: 'a-mon-1', label: 'SRM Check', prompt: 'Check for sample ratio mismatch in current allocations.' },
    { id: 'a-mon-2', label: 'Health Monitor', prompt: 'Run health monitor on all active pipelines.' },
  ],
  analysis: [
    { id: 'a-ana-1', label: 'Causal DiD', prompt: 'Run causal difference-in-differences analysis.' },
    { id: 'a-ana-2', label: 'Paradox Check', prompt: "Run Simpson's Paradox check on aggregated metrics." },
  ],
}

const MODULE_PILLS: Partial<Record<ModuleId, ActionPill[]>> = {
  'power-calculator': [
    { id: 'pc-1', label: 'Run Power Calc', prompt: 'Compute required sample size for 80% power at α=0.05.' },
    { id: 'pc-2', label: 'Proceed to Audience', prompt: 'Proceed to audience selection.' },
  ],
  'opportunity-sizing': [
    { id: 'os-1', label: 'Size Market', prompt: 'Calculate addressable market size with CI bounds.' },
    { id: 'os-2', label: 'Proceed to Metrics', prompt: 'Proceed to metrics tracking.' },
  ],
  'metrics-tracking': [
    { id: 'mt-1', label: 'Set Feature', prompt: 'Set feature description and experiment maturity for metrics tracking.' },
    { id: 'mt-2', label: 'Proceed to Type', prompt: 'Proceed to experiment type.' },
  ],
  'experiment-type': [
    { id: 'et-1', label: 'Recommend Type', prompt: 'Recommend A/B or A/B/C for this digital experiment.' },
    { id: 'et-2', label: 'Proceed to Power', prompt: 'Proceed to power calculator.' },
  ],
  'audience-selection': [
    { id: 'as-1', label: 'Select Audience', prompt: 'Configure digital audience segments and traffic split.' },
    { id: 'as-2', label: 'Proceed to Brief', prompt: 'Proceed to brief generator.' },
  ],
  'brief-generator': [
    { id: 'bg-1', label: 'Draft Brief', prompt: 'Generate experiment brief from current specifications.' },
    { id: 'bg-2', label: 'Draft Hypothesis Spec', prompt: 'Draft formal hypothesis linked to the experiment brief.' },
  ],
  'data-validation': [
    { id: 'dv-1', label: 'Null Check', prompt: 'Run null value and completeness checks.' },
    { id: 'dv-2', label: 'Schema Scan', prompt: 'Validate schema integrity across source tables.' },
  ],
  'schema-discovery': [
    { id: 'sd-1', label: 'Map Tables', prompt: 'Map all source tables and their relationships.' },
  ],
  'causal-did': [
    { id: 'cd-1', label: 'Run DiD', prompt: 'Execute causal DiD model with treatment effects.' },
  ],
  'simpsons-paradox': [
    { id: 'sp-1', label: 'Detect Paradox', prompt: "Check for Simpson's Paradox across segments." },
  ],
  'health-monitor': [
    { id: 'hm-1', label: 'Pipeline Status', prompt: 'Show real-time pipeline health metrics.' },
  ],
}

export function getActionPills(
  persona: Persona,
  phase: Phase,
  moduleId: ModuleId | null,
): ActionPill[] {
  if (persona === 'executive') {
    return EXECUTIVE_PILLS[phase] ?? EXECUTIVE_PILLS.auto ?? []
  }
  if (moduleId && MODULE_PILLS[moduleId]) {
    return MODULE_PILLS[moduleId]!
  }
  const mod = MODULE_BY_ID[phase as ModuleId]
  if (mod && MODULE_PILLS[mod.id]) {
    return MODULE_PILLS[mod.id]!
  }
  return ANALYST_BUCKET_PILLS[mod?.executivePhase ?? phase] ?? ANALYST_BUCKET_PILLS.auto ?? []
}

export function getWorkspaceStats(): WorkspaceStat[] {
  return [...WORKSPACE_STATS]
}

export function getModuleConsoleLogs(moduleId: ModuleId | null, experiment: string): string[] {
  const mod = moduleId ? MODULE_BY_ID[moduleId] : null
  const base = [
    `[INFO]  pipeline.init — Experiment "${experiment}" loaded`,
    `[INFO]  schema.validate — 14 tables verified, 0 anomalies`,
  ]
  if (mod) {
    return [
      ...base,
      `[INFO]  ${mod.id} — Module "${mod.label}" initialized`,
      `[INFO]  ${mod.id} — ${mod.label} ran successfully in ${mod.mockDuration}`,
      `[SQL]   SELECT treatment, control, lift FROM exp_results WHERE exp_id = '${experiment.replace(/\s/g, '_').toLowerCase()}'`,
      `[WARN]  srm.check — Minor allocation drift detected (δ=0.003)`,
      `[DEBUG] cache.refresh — Insights snapshot updated for ${mod.label}`,
    ]
  }
  return [
    ...base,
    '[WARN]  srm.check — Minor allocation drift detected (δ=0.003)',
    '[INFO]  causal.did — Treatment effect: +0.042 (p=0.003)',
    '[INFO]  health.monitor — All pipelines operational',
  ]
}

export function isModuleId(value: string): value is ModuleId {
  return value in MODULE_BY_ID
}
