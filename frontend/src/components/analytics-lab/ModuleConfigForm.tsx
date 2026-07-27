import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import type { ModuleId } from '../../context/types'
import { getModuleFormSchema } from '../../data/moduleFormSchemas'
import { getModuleIcon } from '../../data/moduleIcons'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { AppIcon } from '../shared/AppIcon'
import { FormFieldRenderer } from './fields/FormFieldRenderer'
import { ModuleRunButton } from './ModuleRunButton'

interface ModuleConfigFormProps {
  moduleId: ModuleId
}

export function ModuleConfigForm({ moduleId }: ModuleConfigFormProps) {
  const { moduleFormValuesByExperiment } = useMatchView()
  const {
    selectedExperiment,
    updateModuleFormField,
    isFieldHighlighted,
    moduleRunStatus,
  } = useAnalyticsLab()

  const mod = MODULE_BY_ID[moduleId]
  const ModIcon = getModuleIcon(moduleId)
  const schema = getModuleFormSchema(moduleId, selectedExperiment)
  const values = moduleFormValuesByExperiment[selectedExperiment]?.[moduleId] ?? {}

  return (
    <div className="flex min-h-0 flex-1 flex-col px-3 py-3">
      <header className="mb-3 shrink-0 border-b border-border-muted/12 pb-2.5">
        <p className="type-overline">
          Module
        </p>
        <h3 className="mt-1 flex items-center gap-1.5 text-sm font-semibold leading-tight tracking-tight text-text-primary">
          <AppIcon icon={ModIcon} size="xs" className="shrink-0 text-border-muted" aria-hidden="true" />
          <span className="truncate">{mod.label}</span>
        </h3>
        <p className="type-subtitle mt-0.5 truncate">{mod.phaseLabel}</p>
      </header>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-3.5 overflow-y-auto pr-0.5">
          {schema.fields.map((field) => (
            <FormFieldRenderer
              key={field.key}
              field={field}
              value={values[field.key] ?? field.defaultValue}
              highlighted={isFieldHighlighted(field.key)}
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
    </div>
  )
}
