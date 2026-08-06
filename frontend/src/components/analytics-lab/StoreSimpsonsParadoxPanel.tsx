import { useEffect, useRef, useState } from 'react'
import { Split, Loader2, TriangleAlert, CheckCircle2 } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { useAnalyticsLab } from '../../context/useAnalyticsLab'
import { AppIcon } from '../shared/AppIcon'
import { type SimpsonsParadoxResult, simulateSimpsonsParadoxCheck } from '../../data/storeCausalRoi'

const DIMENSION_LABELS: Record<string, string> = { format: 'Store Format', size: 'Store Size Tier', climate: 'Climate Zone' }

export function StoreSimpsonsParadoxPanel() {
  const { moduleFormValuesByExperiment, updateModuleFormField, moduleRunStatus, labModuleId } = useMatchView()
  const { selectedExperiment } = useAnalyticsLab()
  const values = (moduleFormValuesByExperiment[selectedExperiment] ?? {}) as Record<string, Record<string, unknown>>
  const rollout = values['store-rollout-targeting'] ?? {}
  const testStoreCount = typeof rollout.targetStoreCount === 'number' ? rollout.targetStoreCount : 500

  const [result, setResult] = useState<SimpsonsParadoxResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Auto-run simulation when a chat-triggered module run completes for simpsons-paradox
  const prevRunStatusRef = useRef<string>(moduleRunStatus)
  useEffect(() => {
    if (
      prevRunStatusRef.current === 'running' &&
      moduleRunStatus === 'success' &&
      labModuleId === 'simpsons-paradox' &&
      !isRunning
    ) {
      setIsRunning(true)
      setResult(null)
      simulateSimpsonsParadoxCheck(testStoreCount)
        .then((r) => {
          setResult(r)
          updateModuleFormField('simpsons-paradox' as any, 'lastResult', r)
        })
        .catch(() => setError('Auto-run failed — try running manually.'))
        .finally(() => setIsRunning(false))
    }
    prevRunStatusRef.current = moduleRunStatus
  }, [moduleRunStatus, labModuleId])

  const run = async () => {
    setError(null)
    setIsRunning(true)
    setResult(null)
    try {
      const r = await simulateSimpsonsParadoxCheck(testStoreCount)
      setResult(r)
      updateModuleFormField('simpsons-paradox' as any, 'lastResult', r)
    } catch {
      setError('Subgroup scan failed to run — try again.')
    } finally {
      setIsRunning(false)
    }
  }

  const maxAbs = result ? Math.max(1, ...result.subgroups.map((s) => Math.abs(s.liftPercent)), Math.abs(result.overallLiftPercent)) : 1

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <p className="type-overline mb-1">Automated Subgroup Scan</p>
          <p className="text-micro text-text-secondary leading-relaxed">
            Checks lift across Store Formats (Urban/Suburban/Rural), Store Size Tiers (Small/Medium/Large),
            Climate Zones, and Quarterly G.O.L.D. Tiers — protects against "Aggregate Traps" where a test
            looks positive overall but is failing across most store types.
          </p>
        </div>

        {error && <p className="text-micro text-red-600">{error}</p>}

        {result && !isRunning && (
          <>
            {result.paradoxDetected ? (
              <div className="flex items-start gap-2 rounded-[8px] border border-red-500/30 bg-red-50/40 px-3 py-2.5">
                <AppIcon icon={TriangleAlert} size="sm" className="mt-0.5 shrink-0 text-red-600" />
                <div>
                  <p className="text-xs font-semibold text-red-700">Simpson's Paradox Detected</p>
                  <p className="mt-0.5 text-micro text-red-700">
                    Overall chain lift is positive ({result.overallLiftPercent >= 0 ? '+' : ''}{result.overallLiftPercent}%),
                    but negative across {result.paradoxSegment}. Recommend targeted rollout rather than
                    full-fleet expansion.
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 rounded-[8px] bg-green-100 px-3 py-2 text-xs font-medium text-green-700">
                <AppIcon icon={CheckCircle2} size="xs" /> No paradox detected — lift direction is consistent across subgroups.
              </div>
            )}

            <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="type-overline">Overall Lift</p>
                <span className="text-sm font-bold tabular-nums text-text-primary">{result.overallLiftPercent >= 0 ? '+' : ''}{result.overallLiftPercent}%</span>
              </div>
              {['format', 'size', 'climate'].map((dim) => (
                <div key={dim} className="mb-2 last:mb-0">
                  <p className="mb-1 text-micro font-medium text-text-secondary">{DIMENSION_LABELS[dim]}</p>
                  <div className="flex flex-col gap-1">
                    {result.subgroups.filter((s) => s.dimension === dim).map((s) => {
                      const widthPct = (Math.abs(s.liftPercent) / maxAbs) * 100
                      return (
                        <div key={s.segment} className="flex items-center gap-2">
                          <span className="w-16 shrink-0 text-micro text-text-secondary">{s.segment}</span>
                          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-hover/60">
                            <div className={`h-full ${s.liftPercent >= 0 ? 'bg-green-500' : 'bg-red-500'}`} style={{ width: `${Math.max(widthPct, 4)}%` }} />
                          </div>
                          <span className={`w-12 shrink-0 text-right text-micro tabular-nums ${s.liftPercent >= 0 ? 'text-green-700' : 'text-red-600'}`}>
                            {s.liftPercent >= 0 ? '+' : ''}{s.liftPercent}%
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="mt-3 shrink-0 border-t border-border-muted/12 pt-3">
        <button type="button" onClick={run} disabled={isRunning}
          className="focus-ring flex w-full items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
          {isRunning ? (<><AppIcon icon={Loader2} size="xs" className="animate-spin" /> Scanning subgroups…</>) : (<><AppIcon icon={Split} size="xs" /> Run Heterogeneity Check</>)}
        </button>
      </div>
    </div>
  )
}
