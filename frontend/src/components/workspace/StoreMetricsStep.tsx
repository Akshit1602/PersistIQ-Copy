/**
 * Store Channel Metrics Step (Step 3)
 *
 * Uses getStoreKpisForRole() from storeMetricCatalog instead of
 * the digital channel's getKpisForRole(). Groups metrics by category
 * (Financial, Traffic & Conversion, Basket Mechanics, etc.)
 */

import { CheckCircle2 } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import { MultiSelectDropdown } from '../shared/MultiSelectDropdown'
import {
  getStoreKpisForRole,
  getStoreMetricInputsForSelection,
  STORE_METRIC_BY_ID,
  STORE_KPI_SEARCH_KEYWORDS,
  type StoreMetricCategory,
} from '../../data/storeMetricCatalog'
import type { MetricInputField } from '../../data/metricCatalog'
import type { FieldSuggestion } from '../../data/inputSuggestions'
import { SuggestedValueBadge } from '../shared/SuggestedValueBadge'

interface MetricsState {
  primaryMetricIds: string[]
  secondaryMetricIds: string[]
  guardrailMetricIds: string[]
  metricInputs: Record<string, Record<string, string>>
  guardrailThreshold?: number | null
  guardrailDirection?: 'below' | 'above'
}

interface Props {
  metrics: MetricsState
  onChange: (partial: Partial<MetricsState>) => void
  /** Field-keyed suggestions; store KPIs are only proposed where the feed
   *  already reports a baseline for them. */
  suggestions?: Record<string, FieldSuggestion>
}

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
const selectClass = `${inputClass} appearance-none bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat pr-8`
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"

/** Category badge colors */
const CATEGORY_COLORS: Record<StoreMetricCategory, string> = {
  Financial: 'bg-blue-100 text-blue-700',
  'Traffic & Conversion': 'bg-emerald-100 text-emerald-700',
  'Basket Mechanics': 'bg-purple-100 text-purple-700',
  'Supply Chain': 'bg-amber-100 text-amber-700',
  'Environmental Confounders': 'bg-gray-100 text-gray-600',
  Guardrails: 'bg-red-100 text-red-700',
}

/** Renders store KPI ids as their catalog labels when offering a suggestion. */
function StoreMetricSuggestion({
  suggestion,
  value,
  onApply,
}: {
  suggestion?: FieldSuggestion
  value: string[]
  onApply: (ids: string[]) => void
}) {
  if (!suggestion || !Array.isArray(suggestion.value) || suggestion.value.length === 0) return null
  return (
    <SuggestedValueBadge
      suggestion={suggestion}
      value={value}
      formatValue={(v) =>
        (Array.isArray(v) ? v : [v])
          .map((id) => STORE_METRIC_BY_ID[String(id)]?.label ?? id)
          .join(', ')
      }
      onApply={(ids) => onApply((ids as string[]) ?? [])}
    />
  )
}

export function StoreMetricsStep({ metrics, onChange, suggestions = {} }: Props) {
  const primaryOptions = getStoreKpisForRole('primary').map((k) => ({
    id: k.id,
    label: k.label,
    description: `[${k.category}] ${k.description}`,
    disabled: metrics.secondaryMetricIds.includes(k.id),
    keywords: STORE_KPI_SEARCH_KEYWORDS[k.id],
  }))

  const secondaryOptions = getStoreKpisForRole('secondary').map((k) => ({
    id: k.id,
    label: k.label,
    description: `[${k.category}] ${k.description}`,
    disabled: metrics.primaryMetricIds.includes(k.id),
    keywords: STORE_KPI_SEARCH_KEYWORDS[k.id],
  }))

  const guardrailOptions = getStoreKpisForRole('guardrail').map((k) => ({
    id: k.id,
    label: k.label,
    description: k.description,
  }))

  const handlePrimaryChange = (primaryMetricIds: string[]) => {
    const dropped = metrics.primaryMetricIds.filter((id) => !primaryMetricIds.includes(id))
    const metricInputs = { ...metrics.metricInputs }
    for (const id of dropped) delete metricInputs[id]
    onChange({ primaryMetricIds, metricInputs })
  }

  const handleSecondaryChange = (secondaryMetricIds: string[]) => {
    const dropped = metrics.secondaryMetricIds.filter((id) => !secondaryMetricIds.includes(id))
    const metricInputs = { ...metrics.metricInputs }
    for (const id of dropped) delete metricInputs[id]
    onChange({ secondaryMetricIds, metricInputs })
  }

  const selectedInputs = getStoreMetricInputsForSelection([
    ...metrics.primaryMetricIds,
    ...metrics.secondaryMetricIds,
  ])

  return (
    <div className="flex flex-col gap-3.5">
      {/* Header */}
      <div>
        <p className="text-sm font-semibold text-text-primary">Metrics & Tracking</p>
        <p className="mt-0.5 text-xs text-text-secondary">
          Select primary, secondary, and guardrail KPIs from the store metric catalog.
          Primary/secondary metrics require baseline inputs for power analysis.
        </p>
      </div>

      {/* Primary Metrics */}
      <div>
        <div className="flex items-center gap-1 mb-1">
          <p className="type-overline">Primary metrics</p>
          <span className="ml-0.5 text-red-600 text-xs" aria-label="required">*</span>
        </div>
        <p className="mb-1 text-micro text-text-secondary">
          Target KPIs for the hypothesis — at least one required
        </p>
        <MultiSelectDropdown
          aria-label="Primary store metrics"
          placeholder="Select primary KPIs…"
          options={primaryOptions}
          value={metrics.primaryMetricIds}
          onChange={handlePrimaryChange}
        />
        <StoreMetricSuggestion
          suggestion={suggestions.primaryMetrics}
          value={metrics.primaryMetricIds}
          onApply={handlePrimaryChange}
        />
        {/* Show category badges for selected */}
        {metrics.primaryMetricIds.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {metrics.primaryMetricIds.map((id) => {
              const m = STORE_METRIC_BY_ID[id]
              if (!m) return null
              return (
                <span
                  key={id}
                  className={`rounded-xs px-1.5 py-0.5 text-micro font-medium ${CATEGORY_COLORS[m.category]}`}
                >
                  {m.label}
                </span>
              )
            })}
          </div>
        )}
      </div>

      {/* Secondary Metrics */}
      <div>
        <p className="type-overline mb-0.5">Secondary metrics</p>
        <p className="mb-1 text-micro text-text-secondary">
          Supporting signals — optional
        </p>
        <MultiSelectDropdown
          aria-label="Secondary store metrics"
          placeholder="Select secondary KPIs…"
          options={secondaryOptions}
          value={metrics.secondaryMetricIds}
          onChange={handleSecondaryChange}
        />
        <StoreMetricSuggestion
          suggestion={suggestions.secondaryMetrics}
          value={metrics.secondaryMetricIds}
          onApply={handleSecondaryChange}
        />
      </div>

      {/* KPI Baseline Inputs */}
      {selectedInputs.length > 0 && (
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/70 px-3 py-3">
          <p className="type-overline mb-2">KPI Baseline Inputs</p>
          <p className="mb-3 text-micro text-text-secondary">
            Provide baseline values for power analysis and MDE calculation.
          </p>
          <div className="flex flex-col gap-3.5">
            {selectedInputs.map(({ kpiId, label, inputs: fields }) => (
              <div key={kpiId} className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <p className="text-xs font-semibold text-text-primary">{label}</p>
                  {STORE_METRIC_BY_ID[kpiId] && (
                    <span
                      className={`rounded-xs px-1 py-0.5 text-micro ${CATEGORY_COLORS[STORE_METRIC_BY_ID[kpiId].category]}`}
                    >
                      {STORE_METRIC_BY_ID[kpiId].category}
                    </span>
                  )}
                  {STORE_METRIC_BY_ID[kpiId] &&
                    (STORE_METRIC_BY_ID[kpiId].format === 'percentage' || STORE_METRIC_BY_ID[kpiId].format === 'decimal') && (
                      <span
                        className="rounded-xs bg-indigo-100 px-1 py-0.5 text-micro font-medium text-indigo-700"
                        title="Ratio metric — delta-method / ratio-of-sums correction applied, not naive averaging"
                      >
                        Ratio metric — delta-method applied
                      </span>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {fields.map((field: MetricInputField) => (
                    <div key={`${kpiId}-${field.key}`} className="min-w-0">
                      <label className="type-caption mb-0.5 block">
                        {field.label}
                        {field.required !== false && (
                          <span className="ml-0.5 text-red-600">*</span>
                        )}
                      </label>
                      <input
                        type={field.type === 'number' ? 'number' : 'text'}
                        className={inputClass}
                        value={metrics.metricInputs[kpiId]?.[field.key] ?? ''}
                        placeholder={field.placeholder}
                        onChange={(e) => {
                          const next = {
                            ...metrics.metricInputs,
                            [kpiId]: {
                              ...(metrics.metricInputs[kpiId] ?? {}),
                              [field.key]: e.target.value,
                            },
                          }
                          onChange({ metricInputs: next })
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Guardrail Metrics */}
      <div>
        <p className="type-overline mb-0.5">Guardrail metrics</p>
        <p className="mb-2 text-micro text-text-secondary">
          Select the mandatory floor metric this initiative must not degrade
        </p>
        <select
          className={selectClass}
          style={{ backgroundImage: selectChevronBg }}
          value={metrics.guardrailMetricIds[0] ?? ''}
          onChange={(e) => onChange({ guardrailMetricIds: e.target.value ? [e.target.value] : [] })}
        >
          <option value="">Select a guardrail KPI…</option>
          {guardrailOptions.map((g) => (
            <option key={g.id} value={g.id}>{g.label}</option>
          ))}
        </select>
        {metrics.guardrailMetricIds[0] && (
          <>
            <p className="mt-1.5 flex items-start gap-1.5 text-micro text-text-secondary leading-relaxed">
              <AppIcon icon={CheckCircle2} size="xs" className="mt-0.5 shrink-0 text-green-600" />
              {guardrailOptions.find((g) => g.id === metrics.guardrailMetricIds[0])?.description}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Alert Threshold</label>
                <input
                  type="number"
                  className={inputClass}
                  placeholder="e.g. 5"
                  value={metrics.guardrailThreshold ?? ''}
                  onChange={(e) => onChange({ guardrailThreshold: e.target.value === '' ? null : Number(e.target.value) })}
                />
              </div>
              <div className="min-w-0">
                <label className="type-caption mb-0.5 block">Alert Trigger</label>
                <select
                  className={selectClass}
                  style={{ backgroundImage: selectChevronBg }}
                  value={metrics.guardrailDirection ?? 'below'}
                  onChange={(e) => onChange({ guardrailDirection: e.target.value as 'below' | 'above' })}
                >
                  <option value="below">Alert if it drops below threshold</option>
                  <option value="above">Alert if it rises above threshold</option>
                </select>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
