import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BarChart3,
  BookOpen,
  Briefcase,
  Calculator,
  Cog,
  Database,
  Eye,
  FileText,
  GitCompare,
  HeartPulse,
  Layers,
  LineChart,
  ScanSearch,
  Scale,
  ShieldCheck,
  Sigma,
  Target,
  TrendingUp,
  Users,
  FlaskConical,
  Zap,
} from 'lucide-react'
import type { ModuleId, ModulePhaseKey } from '../context/types'

export const PHASE_ICONS: Record<ModulePhaseKey, LucideIcon> = {
  foundation: ScanSearch,
  preplanning: Briefcase,
  monitoring: Activity,
  causal: LineChart,
}

export const MODULE_ICONS: Record<ModuleId, LucideIcon> = {
  'data-validation': ShieldCheck,
  'dimension-setup': Layers,
  'distribution-shift': TrendingUp,
  'pipeline-health': HeartPulse,
  'schema-discovery': Database,
  watchtower: Eye,
  'opportunity-sizing': Target,
  'metrics-tracking': BarChart3,
  'experiment-type': FlaskConical,
  'power-calculator': Calculator,
  'audience-selection': Users,
  'balance-diagnostics': Scale,
  'brief-generator': FileText,
  'experiment-analysis': BarChart3,
  'health-monitor': HeartPulse,
  'sequential-testing': Zap,
  'causal-did': GitCompare,
  forecasting: TrendingUp,
  'learnings-repository': BookOpen,
  'roi-synthesis': Sigma,
  'simpsons-paradox': GitCompare,
}

export function getPhaseIcon(phaseId: ModulePhaseKey): LucideIcon {
  return PHASE_ICONS[phaseId]
}

export function getModuleIcon(moduleId: ModuleId): LucideIcon {
  return MODULE_ICONS[moduleId] ?? Cog
}
