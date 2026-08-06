import { useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, Radar } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import {
  type StoreHypothesisExtras as StoreHypothesisExtrasState,
  type InitiativeDomain,
  type DosageType,
  DOMAIN_OPTIONS,
  DOSAGE_TYPE_OPTIONS,
  DOMAIN_DOSAGE_TYPES,
  simulateShadowInitiativeCheck,
} from '../../data/storeHypothesisExtras'

interface Props {
  extras: StoreHypothesisExtrasState
  hypothesisName: string
  onChange: (partial: Partial<StoreHypothesisExtrasState>) => void
}

const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
const selectClass = `${inputClass} appearance-none bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat pr-8`
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"

export function StoreHypothesisExtras({ extras, hypothesisName, onChange }: Props) {
  const [error, setError] = useState<string | null>(null)
  const dosageTypeMeta = DOSAGE_TYPE_OPTIONS.find((u) => u.value === extras.dosageType)

  const runShadowCheck = async () => {
    setError(null)
    onChange({ isRunningShadowCheck: true, shadowCheckResult: null })
    try {
      const result = await simulateShadowInitiativeCheck(hypothesisName || 'untitled')
      onChange({ isRunningShadowCheck: false, shadowCheckResult: result })
    } catch {
      setError('Shadow-initiative scan failed — try again.')
      onChange({ isRunningShadowCheck: false })
    }
  }

  return (
    <div className="flex flex-col gap-3.5">
      {/* Initiative Domain */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <label className="type-overline mb-0.5 block">
          Initiative Domain <span className="text-red-600">*</span>
        </label>
        <p className="mb-1.5 text-micro text-text-secondary">
          Links this hypothesis to a recognized exposure-ledger domain.
        </p>
        <select
          className={selectClass}
          style={{ backgroundImage: selectChevronBg }}
          value={extras.domain ?? ''}
          onChange={(e) => {
            const domain = (e.target.value || null) as InitiativeDomain | null
            const allowedTypes = domain ? DOMAIN_DOSAGE_TYPES[domain] : null
            onChange({
              domain,
              dosageType: allowedTypes ? allowedTypes[0] : extras.dosageType,
            })
          }}
        >
          <option value="">Select a domain…</option>
          {DOMAIN_OPTIONS.map((a) => (
            <option key={a.value} value={a.value}>{a.label}</option>
          ))}
        </select>
        {extras.domain && (
          <p className="mt-1 text-micro text-text-secondary">
            {DOMAIN_OPTIONS.find((a) => a.value === extras.domain)?.hint}
          </p>
        )}
      </div>

      {/* Dynamic Dosage Configurator */}
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
        <label className="type-overline mb-0.5 block">Dosage</label>
        <p className="mb-1.5 text-micro text-text-secondary">
          {extras.domain
            ? 'Adapted to the selected domain — the exact degree of intervention, not just a treated/control flag.'
            : 'Select an Initiative Domain above to load the right dosage input for that domain.'}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="min-w-0">
            <label className="type-caption mb-0.5 block">Amount</label>
            <input
              type="number"
              className={inputClass}
              value={extras.dosageValue ?? ''}
              placeholder={dosageTypeMeta?.placeholder}
              onChange={(e) => onChange({ dosageValue: e.target.value === '' ? null : Number(e.target.value) })}
            />
          </div>
          <div className="min-w-0">
            <label className="type-caption mb-0.5 block">Type</label>
            <select
              className={selectClass}
              style={{ backgroundImage: selectChevronBg }}
              value={extras.dosageType}
              onChange={(e) => onChange({ dosageType: e.target.value as DosageType })}
            >
              {(extras.domain ? DOMAIN_DOSAGE_TYPES[extras.domain] : DOSAGE_TYPE_OPTIONS.map((o) => o.value)).map((typeValue) => {
                const meta = DOSAGE_TYPE_OPTIONS.find((o) => o.value === typeValue)
                return <option key={typeValue} value={typeValue}>{meta?.label ?? typeValue}</option>
              })}
            </select>
          </div>
        </div>
      </div>

      {/* Shadow Initiative Check */}
      <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
        <div className="flex items-center gap-2">
          <AppIcon icon={Radar} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">Undocumented Initiative Check</p>
        </div>
        <p className="mt-1 text-xs text-text-secondary leading-relaxed">
          Runs a background change-point scan to confirm this is a documented initiative, not an
          unmeasured "shadow" change already affecting the baseline.
        </p>
        <button
          type="button"
          onClick={runShadowCheck}
          disabled={extras.isRunningShadowCheck}
          className="focus-ring mt-3 flex items-center justify-center gap-2 rounded-xs bg-border-muted px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {extras.isRunningShadowCheck ? (
            <>
              <AppIcon icon={Loader2} size="xs" className="animate-spin" />
              Scanning for change points…
            </>
          ) : (
            <>
              <AppIcon icon={Radar} size="xs" />
              Run Shadow Initiative Check
            </>
          )}
        </button>
        {error && <p className="mt-1.5 text-micro text-red-600">{error}</p>}
        {extras.shadowCheckResult && !extras.isRunningShadowCheck && (
          <div
            className={`mt-2.5 rounded-xs px-3 py-2 text-xs font-medium ${
              extras.shadowCheckResult.verdict === 'documented'
                ? 'bg-green-100 text-green-700'
                : 'bg-amber-100 text-amber-700'
            }`}
          >
            <div className="flex items-center gap-1.5">
              <AppIcon
                icon={extras.shadowCheckResult.verdict === 'documented' ? CheckCircle2 : AlertTriangle}
                size="sm"
              />
              {extras.shadowCheckResult.verdict === 'documented'
                ? `No unexplained change points — confidence ${(extras.shadowCheckResult.confidence * 100).toFixed(0)}%`
                : `Possible shadow initiative detected near ${extras.shadowCheckResult.changePointDate} — confidence ${(extras.shadowCheckResult.confidence * 100).toFixed(0)}%`}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
