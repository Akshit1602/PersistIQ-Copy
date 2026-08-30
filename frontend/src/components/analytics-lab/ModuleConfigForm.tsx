import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import type { ModuleId } from '../../context/types'
import { getModuleFormSchema } from '../../data/moduleFormSchemas'
import { getModuleIcon } from '../../data/moduleIcons'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'
import { FormFieldRenderer } from './fields/FormFieldRenderer'
import { ModuleRunButton } from './ModuleRunButton'
import { StoreAudienceModuleRedirect } from './StoreAudienceModuleRedirect'
import { StoreBriefGeneratorPanel } from './StoreBriefGeneratorPanel'
import { StoreBalanceDiagnosticsPanel } from './StoreBalanceDiagnosticsPanel'
import { StoreFeedDiagnosticsPanel } from './StoreFeedDiagnosticsPanel'
import { StorePeekingProtectionPanel } from './StorePeekingProtectionPanel'
import { StoreLiftTrajectoryPanel } from './StoreLiftTrajectoryPanel'
import { StoreCausalInferenceEnginePanel } from './StoreCausalInferenceEnginePanel'
import { StoreForecastingPanel } from './StoreForecastingPanel'
import { StoreRoiSynthesisPanel } from './StoreRoiSynthesisPanel'
import { StoreSimpsonsParadoxPanel } from './StoreSimpsonsParadoxPanel'
import { StoreLearningsRepositoryPanel } from './StoreLearningsRepositoryPanel'

interface ModuleConfigFormProps {
  moduleId: ModuleId
}

export function ModuleConfigForm({ moduleId }: ModuleConfigFormProps) {
  const { moduleFormValuesByExperiment, experimentProjectIds, projects, getFieldSuggestions } =
    useMatchView()
  const {
    selectedExperiment,
    updateModuleFormField,
    isFieldHighlighted,
    moduleRunStatus,
  } = useAnalyticsLab()

  const channel = projects.find((p) => p.id === experimentProjectIds[selectedExperiment])?.channel ?? 'digital'
  const isStore = channel === 'store'

  const mod = MODULE_BY_ID[moduleId]
  const ModIcon = getModuleIcon(moduleId)
  const schema = getModuleFormSchema(moduleId, selectedExperiment)
  const values = moduleFormValuesByExperiment[selectedExperiment]?.[moduleId] ?? {}
  const suggestions = getFieldSuggestions(moduleId)

  const STORE_LABEL_OVERRIDES: Record<string, string> = {
    'audience-selection': 'Store Matching & Panel Selection',
    'experiment-analysis': 'Store Feed & Execution Diagnostics',
    'health-monitor': 'Peeking Protection & Futility',
    'sequential-testing': 'In-Flight Lift Trajectory',
    'causal-did': 'Causal Inference Engine',
    'forecasting': 'Forecasting & Counterfactual Predictor',
    'roi-synthesis': 'ROI Synthesis (P&L Money Waterfall)',
    'simpsons-paradox': "Simpson's Paradox & Heterogeneity Checker",
    'learnings-repository': 'Learnings & Meta-Analysis Repository',
  }
  const displayLabel = isStore ? (STORE_LABEL_OVERRIDES[moduleId] ?? mod.label) : mod.label

  return (
    <div className="flex min-h-0 flex-1 flex-col px-3 py-3">
      <header className="mb-3 shrink-0 border-b border-border-muted/12 pb-2.5">
        <p className="type-overline">
          Module
        </p>
        <h3 className="mt-1 flex items-center gap-1.5 text-sm font-semibold leading-tight tracking-tight text-text-primary">
          <AppIcon icon={ModIcon} size="xs" className="shrink-0 text-border-muted" aria-hidden="true" />
          <span className="truncate">{displayLabel}</span>
        </h3>
        <p className="type-subtitle mt-0.5 truncate">{mod.phaseLabel}</p>
      </header>

      {isStore && moduleId === 'audience-selection' ? (
        <StoreAudienceModuleRedirect />
      ) : isStore && moduleId === 'brief-generator' ? (
        <StoreBriefGeneratorPanel />
      ) : isStore && moduleId === 'balance-diagnostics' ? (
        <StoreBalanceDiagnosticsPanel />
      ) : isStore && moduleId === 'experiment-analysis' ? (
        <StoreFeedDiagnosticsPanel />
      ) : isStore && moduleId === 'health-monitor' ? (
        <StorePeekingProtectionPanel />
      ) : isStore && moduleId === 'sequential-testing' ? (
        <StoreLiftTrajectoryPanel />
      ) : isStore && moduleId === 'causal-did' ? (
        <StoreCausalInferenceEnginePanel />
      ) : isStore && moduleId === 'forecasting' ? (
        <StoreForecastingPanel />
      ) : isStore && moduleId === 'roi-synthesis' ? (
        <StoreRoiSynthesisPanel />
      ) : isStore && moduleId === 'simpsons-paradox' ? (
        <StoreSimpsonsParadoxPanel />
      ) : isStore && moduleId === 'learnings-repository' ? (
        <StoreLearningsRepositoryPanel />
      ) : (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-3.5 overflow-y-auto pr-0.5">
          {schema.fields.map((field) => (
            <FormFieldRenderer
              key={field.key}
              field={field}
              value={values[field.key] ?? field.defaultValue}
              highlighted={isFieldHighlighted(field.key)}
              suggestion={suggestions[field.key]}
              onChange={(key, value) => updateModuleFormField(moduleId, key, value)}
            />
          ))}

          {moduleRunStatus === 'running' && (
            <div className="flex items-center gap-2 rounded-xs border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5 text-micro text-amber-800">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
              Running — results will appear in chat when complete
            </div>
          )}
        </div>

        <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
          <ModuleRunButton moduleId={moduleId} />
          <p className="mt-1.5 text-center text-micro text-text-secondary">Ctrl+Enter to run</p>
        </div>
      </div>
      )}
    </div>
  )
}
