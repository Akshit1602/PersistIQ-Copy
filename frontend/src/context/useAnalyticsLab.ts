import { useCallback, useMemo } from 'react'
import { useMatchView } from './MatchViewContext'
import type { ModuleId } from './types'

/**
 * Unified Analytics Lab state slice — single source of truth for
 * "Chat Proposes, Panel Disposes" bidirectional synchronization.
 */
export function useAnalyticsLab() {
  const ctx = useMatchView()

  const activeParams = useMemo(() => {
    if (!ctx.labModuleId) return {}
    return ctx.moduleFormValuesByExperiment[ctx.selectedExperiment]?.[ctx.labModuleId] ?? {}
  }, [ctx.labModuleId, ctx.moduleFormValuesByExperiment, ctx.selectedExperiment])

  const updateField = useCallback(
    (key: string, value: unknown) => {
      if (!ctx.labModuleId) return
      ctx.updateModuleFormField(ctx.labModuleId, key, value)
    },
    [ctx],
  )

  const activateModule = useCallback(
    (moduleId: ModuleId, expandPanel = true) => {
      if (expandPanel && ctx.analyticsLabCollapsed) {
        ctx.toggleAnalyticsLabCollapsed()
      }
      ctx.selectLabModule(moduleId)
    },
    [ctx],
  )

  const injectFromNlp = useCallback(
    (moduleId: ModuleId, params: Record<string, unknown>, touchedFields: string[]) => {
      ctx.injectNlpParameters(moduleId, params, touchedFields)
    },
    [ctx],
  )

  const getLockedSnapshot = useCallback(
    (moduleId?: ModuleId) => {
      const id = moduleId ?? ctx.labModuleId
      if (!id) return {}
      return ctx.getLockedModuleSnapshot(id)
    },
    [ctx],
  )

  const runFromPanel = useCallback(() => {
    ctx.runActiveLabModule()
  }, [ctx])

  const isFieldHighlighted = useCallback(
    (fieldKey: string) => ctx.highlightedFieldKeys.includes(fieldKey),
    [ctx.highlightedFieldKeys],
  )

  return {
    labModuleId: ctx.labModuleId,
    labPanelView: ctx.labPanelView,
    selectedExperiment: ctx.selectedExperiment,
    moduleRunStatus: ctx.moduleRunStatus,
    analyticsLabCollapsed: ctx.analyticsLabCollapsed,
    activeParams,
    highlightedFieldKeys: ctx.highlightedFieldKeys,
    updateField,
    activateModule,
    injectFromNlp,
    getLockedSnapshot,
    runFromPanel,
    isFieldHighlighted,
    updateModuleFormField: ctx.updateModuleFormField,
  }
}
