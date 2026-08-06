import { useMemo } from 'react'
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Info, Waves, Target as TargetIcon } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import {
  type StoreOpportunitySizing,
  computeStoreOpportunityOutputs,
  formatCurrency,
  formatRoiPercent,
  getRoiStatus,
  SCALE_FIELDS,
  METRIC_FIELDS,
  FINANCIAL_FIELDS,
  computeVisitLagRampFactor,
  type SizingFieldDef,
} from '../../data/storeHypothesisValidator'

interface Props {
  inputs: StoreOpportunitySizing
  onChange: (partial: Partial<StoreOpportunitySizing>) => void
}

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'

function FieldWithLabel({
  field,
  value,
  onChange,
}: {
  field: SizingFieldDef
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1 mb-1">
        <label className="type-overline block">{field.label}</label>
        {field.info && (
          <span className="group relative inline-flex">
            <button
              type="button"
              className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-text-secondary hover:text-border-muted"
              aria-label={field.info}
            >
              <AppIcon icon={Info} size="xs" />
            </button>
            <span
              role="tooltip"
              className="pointer-events-none absolute left-0 top-full z-30 mt-1 w-[180px] rounded-xs border border-border-muted/20 bg-text-primary px-2 py-1.5 text-micro text-white opacity-0 shadow-md group-hover:opacity-100"
            >
              {field.info}
            </span>
          </span>
        )}
      </div>
      <div className="relative">
        {field.prefix && (
          <span className="absolute inset-y-0 left-2 flex items-center text-xs text-text-secondary">
            {field.prefix}
          </span>
        )}
        <input
          type="number"
          className={`${inputClass} ${field.prefix ? 'pl-6' : ''} ${field.suffix ? 'pr-16' : ''}`}
          value={value}
          min={field.min}
          max={field.max}
          step={field.step}
          placeholder={field.placeholder}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
        />
        {field.suffix && (
          <span className="absolute inset-y-0 right-2 flex items-center text-micro text-text-secondary">
            {field.suffix}
          </span>
        )}
      </div>
    </div>
  )
}

export function StoreOpportunitySizingStep({ inputs, onChange }: Props) {
  // Real-time calculation card outputs
  const outputs = useMemo(() => computeStoreOpportunityOutputs(inputs), [inputs])
  const roiStatus = getRoiStatus(outputs.projectedNetRoi)

  // Helpers to update nested fields
  const patchScale = (key: string, value: number) =>
    onChange({ scale: { ...inputs.scale, [key]: value } })
  const patchMetrics = (key: string, value: number) =>
    onChange({ metrics: { ...inputs.metrics, [key]: value } })
  const patchFinancials = (key: string, value: number) =>
    onChange({ financials: { ...inputs.financials, [key]: value } })
  const patchAdvancedDrivers = (partial: Partial<typeof inputs.advancedDrivers>) =>
    onChange({ advancedDrivers: { ...inputs.advancedDrivers, ...partial } })

  // Map field key to current value
  const readNumber = (record: object, key: string) => {
    const value = (record as Record<string, unknown>)[key]
    return typeof value === 'number' ? value : 0
  }
  const getScaleValue = (key: string) => readNumber(inputs.scale, key)
  const getMetricValue = (key: string) => readNumber(inputs.metrics, key)
  const getFinancialValue = (key: string) => readNumber(inputs.financials, key)

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <p className="text-sm font-semibold text-text-primary">Opportunity Sizing</p>
        <p className="mt-0.5 text-xs text-text-secondary">
          Quantify the business value of this store initiative before committing resources.
        </p>
      </div>

      {/* ─── Row 1: Scale & Time (The Foundation) ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <p className="type-overline mb-2 text-text-secondary">Scale & Time</p>
        <div className="grid grid-cols-3 gap-3">
          {SCALE_FIELDS.map((field) => (
            <FieldWithLabel
              key={field.key}
              field={field}
              value={getScaleValue(field.key)}
              onChange={(v) => patchScale(field.key, v)}
            />
          ))}
        </div>
      </div>

      {/* ─── Row 2: Store Metrics (The Levers) ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <p className="type-overline mb-2 text-text-secondary">Store Metrics</p>
        <div className="grid grid-cols-2 gap-3">
          {/* AUR (full width on first row) */}
          <FieldWithLabel
            field={METRIC_FIELDS[0]} // baselineAur
            value={getMetricValue(METRIC_FIELDS[0].key)}
            onChange={(v) => patchMetrics(METRIC_FIELDS[0].key, v)}
          />
          <div /> {/* spacer */}

          {/* CVR: Baseline → Target Lift */}
          <FieldWithLabel
            field={METRIC_FIELDS[1]} // baselineCvr
            value={getMetricValue(METRIC_FIELDS[1].key)}
            onChange={(v) => patchMetrics(METRIC_FIELDS[1].key, v)}
          />
          <FieldWithLabel
            field={METRIC_FIELDS[2]} // targetCvrLift
            value={getMetricValue(METRIC_FIELDS[2].key)}
            onChange={(v) => patchMetrics(METRIC_FIELDS[2].key, v)}
          />

          {/* UPT: Baseline → Target Lift */}
          <FieldWithLabel
            field={METRIC_FIELDS[3]} // baselineUpt
            value={getMetricValue(METRIC_FIELDS[3].key)}
            onChange={(v) => patchMetrics(METRIC_FIELDS[3].key, v)}
          />
          <FieldWithLabel
            field={METRIC_FIELDS[4]} // targetUptLift
            value={getMetricValue(METRIC_FIELDS[4].key)}
            onChange={(v) => patchMetrics(METRIC_FIELDS[4].key, v)}
          />
        </div>
      </div>

      {/* ─── Row 3: Financials (The Costs) ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <p className="type-overline mb-2 text-text-secondary">Financials</p>
        <div className="grid grid-cols-2 gap-3">
          {FINANCIAL_FIELDS.map((field) => (
            <FieldWithLabel
              key={field.key}
              field={field}
              value={getFinancialValue(field.key)}
              onChange={(v) => patchFinancials(field.key, v)}
            />
          ))}
        </div>
      </div>

      {/* ─── Advanced Drivers: visit lag window, store-native halo/POP cost, iROAS ─── */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <div className="flex items-center gap-2 mb-1">
          <AppIcon icon={Waves} size="sm" />
          <p className="type-overline">Visit Lag & Cross-Effect Drivers</p>
        </div>
        <p className="mb-2 text-micro text-text-secondary leading-relaxed">
          Customers visit sporadically — the full lift ramps in over time, and can spill over to
          (or cannibalize) other categories, and every promo has a real in-store cost.
        </p>
        <div className="mb-3">
          <label className="type-caption mb-0.5 block">Customer Visit Lag Window (weeks)</label>
          <input
            type="range"
            min={4}
            max={13}
            step={1}
            value={inputs.advancedDrivers.visitLagWeeks}
            onChange={(e) => patchAdvancedDrivers({ visitLagWeeks: Number(e.target.value) })}
            className="w-full"
          />
          <p className="mt-1 text-xs tabular-nums text-text-primary">
            {inputs.advancedDrivers.visitLagWeeks} weeks ({(computeVisitLagRampFactor(inputs.advancedDrivers.visitLagWeeks) * 100).toFixed(0)}% of steady-state lift realized)
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="min-w-0">
            <label className="type-caption mb-0.5 block">Cross-Category Store Halo ($)</label>
            <input
              type="number"
              className={inputClass}
              value={inputs.advancedDrivers.crossCategoryStoreHaloDollars}
              placeholder="e.g. 15000"
              onChange={(e) => patchAdvancedDrivers({ crossCategoryStoreHaloDollars: Number(e.target.value) || 0 })}
            />
          </div>
          <div className="min-w-0">
            <label className="type-caption mb-0.5 block">In-Store Circular / POP Cost ($)</label>
            <input
              type="number"
              className={inputClass}
              value={inputs.advancedDrivers.inStoreCircularPopCost}
              placeholder="e.g. 12000"
              onChange={(e) => patchAdvancedDrivers({ inStoreCircularPopCost: Number(e.target.value) || 0 })}
            />
          </div>
          <div className="min-w-0">
            <label className="type-caption mb-0.5 block">Category Cannibalization (%)</label>
            <input
              type="number"
              step="0.5"
              className={inputClass}
              value={inputs.advancedDrivers.categoryCannibalizationPercent * 100}
              placeholder="e.g. 3"
              onChange={(e) => patchAdvancedDrivers({ categoryCannibalizationPercent: (Number(e.target.value) || 0) / 100 })}
            />
          </div>
        </div>
        <div className="mt-2">
          <label className="type-caption mb-0.5 block">Marketing Spend ($, optional — enables iROAS)</label>
          <input
            type="number"
            className={inputClass}
            value={inputs.advancedDrivers.mediaSpend ?? ''}
            placeholder="e.g. 50000"
            onChange={(e) => patchAdvancedDrivers({ mediaSpend: e.target.value === '' ? null : Number(e.target.value) })}
          />
        </div>
      </div>

      {/* ─── Section 2: Dynamic Calculation Card ─── */}
      <div
        className={`rounded-[8px] border px-4 py-4 ${
          roiStatus === 'positive'
            ? 'border-green-500/30 bg-green-50/5'
            : roiStatus === 'negative'
              ? 'border-red-500/30 bg-red-50/5'
              : 'border-border-muted/20 bg-surface-base/50'
        }`}
      >
        <div className="flex items-center gap-2 mb-3">
          <AppIcon icon={BarChart3} size="sm" />
          <p className="text-sm font-semibold text-text-primary">Projected Business Value</p>
          <span className="ml-auto text-micro text-text-secondary italic">Updates live</span>
        </div>

        <div className="grid grid-cols-1 gap-3">
          {/* Incremental Revenue */}
          <div className="flex items-center justify-between rounded-xs bg-surface-raised/60 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <AppIcon icon={DollarSign} size="xs" />
              <span className="text-xs text-text-secondary">Projected Incremental Annual Revenue</span>
            </div>
            <span className="text-sm font-semibold text-text-primary">
              {formatCurrency(outputs.projectedIncrementalAnnualRevenue)}
            </span>
          </div>

          {/* Gross Profit */}
          <div className="flex items-center justify-between rounded-xs bg-surface-raised/60 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <AppIcon icon={TrendingUp} size="xs" />
              <span className="text-xs text-text-secondary">Projected Incremental Gross Profit</span>
            </div>
            <span className="text-sm font-semibold text-text-primary">
              {formatCurrency(outputs.projectedIncrementalGrossProfit)}
            </span>
          </div>

          {/* Net ROI */}
          <div className="flex items-center justify-between rounded-xs bg-surface-raised/60 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <AppIcon icon={roiStatus === 'negative' ? TrendingDown : TrendingUp} size="xs" />
              <span className="text-xs text-text-secondary">Projected Net ROI</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`text-sm font-bold ${
                  roiStatus === 'positive'
                    ? 'text-green-600'
                    : roiStatus === 'negative'
                      ? 'text-red-600'
                      : 'text-text-primary'
                }`}
              >
                {formatCurrency(outputs.projectedNetRoi)}
              </span>
              <span
                className={`rounded-xs px-1.5 py-0.5 text-micro font-medium ${
                  roiStatus === 'positive'
                    ? 'bg-green-100 text-green-700'
                    : roiStatus === 'negative'
                      ? 'bg-red-100 text-red-700'
                      : 'bg-gray-100 text-gray-600'
                }`}
              >
                {formatRoiPercent(outputs.projectedNetRoi, inputs.financials.estimatedInitiativeCost)}
              </span>
            </div>
          </div>

          {/* Ramp-adjusted profit */}
          <div className="flex items-center justify-between rounded-xs bg-surface-raised/60 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <AppIcon icon={Waves} size="xs" />
              <span className="text-xs text-text-secondary">
                Ramp-Adjusted Gross Profit ({inputs.advancedDrivers.visitLagWeeks}-week visit lag window)
              </span>
            </div>
            <span className="text-sm font-semibold text-text-primary">
              {formatCurrency(outputs.rampAdjustedGrossProfit)}
            </span>
          </div>

          {/* Net incremental margin after halo/cannibalization */}
          <div className="flex items-center justify-between rounded-xs bg-surface-raised/60 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <AppIcon icon={TargetIcon} size="xs" />
              <span className="text-xs text-text-secondary">Net Incremental Margin (Halo − Cannibalization − Cost)</span>
            </div>
            <span
              className={`text-sm font-semibold ${
                outputs.netIncrementalMarginAfterHaloCannibalization >= 0 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {formatCurrency(outputs.netIncrementalMarginAfterHaloCannibalization)}
            </span>
          </div>

          {/* iROAS */}
          {outputs.incrementalRoas !== null && (
            <div className="flex items-center justify-between rounded-xs bg-surface-raised/60 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <AppIcon icon={DollarSign} size="xs" />
                <span className="text-xs text-text-secondary">Incremental ROAS (iROAS)</span>
              </div>
              <span className="text-sm font-semibold text-text-primary tabular-nums">
                {outputs.incrementalRoas.toFixed(2)}x
              </span>
            </div>
          )}
        </div>

        {/* Formula breakdown */}
        <p className="mt-3 text-micro text-text-secondary leading-relaxed">
          Revenue = (Traffic × Target CVR × Target UPT × AUR − Baseline) × {inputs.scale.targetStoreCount} stores ×{' '}
          {Math.round(inputs.scale.timeHorizonMonths * (52 / 12))} weeks
        </p>
      </div>
    </div>
  )
}
