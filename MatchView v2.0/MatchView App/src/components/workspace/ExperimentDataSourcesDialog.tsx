import { useEffect, useState } from 'react'
import { Database, Globe, Trash2, X } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { ExperimentDataSourceType } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'

export function ExperimentDataSourcesDialog() {
  const {
    experimentDataSourcesDialogExperiment,
    experimentDataSources,
    closeExperimentDataSourcesDialog,
    updateExperimentDataSources,
    deleteExperiment,
    threadGroups,
  } = useMatchView()

  const experiment = experimentDataSourcesDialogExperiment
  const existing = experiment ? experimentDataSources[experiment] : undefined
  const threadCount =
    threadGroups.find((g) => g.experiment === experiment)?.threads.length ?? 0

  const [sourceType, setSourceType] = useState<ExperimentDataSourceType>('internal')
  const [externalConnection, setExternalConnection] = useState('')

  useEffect(() => {
    if (!experiment) return
    setSourceType(existing?.type ?? 'internal')
    setExternalConnection(existing?.externalConnection ?? '')
  }, [experiment, existing?.type, existing?.externalConnection])

  if (!experiment) return null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateExperimentDataSources(experiment, {
      type: sourceType,
      externalConnection:
        sourceType === 'external' ? externalConnection.trim() || undefined : undefined,
    })
  }

  const handleDeleteExperiment = () => {
    if (
      window.confirm(
        `Delete "${experiment}" and all ${threadCount} conversation${threadCount === 1 ? '' : 's'}? This cannot be undone.`,
      )
    ) {
      deleteExperiment(experiment)
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/25 backdrop-blur-[2px]"
        onClick={closeExperimentDataSourcesDialog}
        aria-label="Close dialog"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="data-sources-title"
        className="relative w-full max-w-md rounded-sm border border-border-muted/20 glass-panel bg-surface-raised p-5 shadow-glow"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="data-sources-title" className="text-sm font-semibold text-text-primary">
              Data sources
            </h2>
            <p className="mt-0.5 truncate text-xs text-text-secondary" title={experiment}>
              {experiment}
            </p>
          </div>
          <button
            type="button"
            onClick={closeExperimentDataSourcesDialog}
            className="focus-ring flex h-7 w-7 shrink-0 items-center justify-center rounded-xs text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
            aria-label="Close"
          >
            <AppIcon icon={X} size="sm" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <fieldset className="space-y-2">
            <legend className="mb-1 text-xs font-medium text-text-primary">Connection type</legend>

            <label className="flex cursor-pointer items-start gap-2.5 rounded-xs border border-border-muted/20 bg-surface-base p-2.5 transition-colors has-[:checked]:border-border-muted/40 has-[:checked]:bg-surface-hover">
              <input
                type="radio"
                name="source-type"
                value="internal"
                checked={sourceType === 'internal'}
                onChange={() => setSourceType('internal')}
                className="mt-0.5"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
                  <AppIcon icon={Database} size="xs" className="text-border-muted" />
                  Internal warehouse
                </span>
                <span className="mt-0.5 block text-xs text-text-secondary">
                  Use MatchView&apos;s managed experiment tables and metrics.
                </span>
              </span>
            </label>

            <label className="flex cursor-pointer items-start gap-2.5 rounded-xs border border-border-muted/20 bg-surface-base p-2.5 transition-colors has-[:checked]:border-border-muted/40 has-[:checked]:bg-surface-hover">
              <input
                type="radio"
                name="source-type"
                value="external"
                checked={sourceType === 'external'}
                onChange={() => setSourceType('external')}
                className="mt-0.5"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
                  <AppIcon icon={Globe} size="xs" className="text-border-muted" />
                  External source
                </span>
                <span className="mt-0.5 block text-xs text-text-secondary">
                  Connect Snowflake, BigQuery, or a custom API endpoint.
                </span>
              </span>
            </label>
          </fieldset>

          {sourceType === 'external' && (
            <div>
              <label
                htmlFor="external-connection"
                className="mb-1 block text-xs font-medium text-text-primary"
              >
                Connection name or URI
              </label>
              <input
                id="external-connection"
                type="text"
                value={externalConnection}
                onChange={(e) => setExternalConnection(e.target.value)}
                placeholder="e.g. snowflake://analytics/prod"
                className="focus-ring w-full rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary"
              />
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={closeExperimentDataSourcesDialog}
              className="focus-ring rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="focus-ring rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
            >
              Save
            </button>
          </div>
        </form>

        <div className="mt-4 border-t border-border-muted/15 pt-3">
          <button
            type="button"
            onClick={handleDeleteExperiment}
            className="focus-ring flex w-full items-center justify-center gap-1.5 rounded-xs border border-red-500/25 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-500/5"
          >
            <AppIcon icon={Trash2} size="xs" />
            Delete experiment &amp; all conversations
          </button>
        </div>
      </div>
    </div>
  )
}
