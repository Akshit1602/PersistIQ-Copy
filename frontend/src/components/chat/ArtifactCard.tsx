import React from 'react'
import { isChartArtifact, type ChartSpec, type UIArtifactCard } from '../../context/types'
import { ArtifactChart } from './ArtifactChart'

/** Keys that carry prose, not a metric — rendered as a caption, never as a stat tile. */
const SUMMARY_KEYS = ['summary', 'interpretation', 'recommendation', 'verdict', 'status', 'basis']

/** Turns `incremental_annual_revenue` into `Incremental Annual Revenue`. */
function humanizeKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bP Value\b/i, 'p-value')
    .replace(/\bSrm\b/i, 'SRM')
    .replace(/\bCi\b/i, 'CI')
    .replace(/\bIor\b/i, 'IOR')
    .replace(/\bAov\b/i, 'AOV')
}

/**
 * Formats a metric value for display. Large counts get thousands separators,
 * anything named like money gets a currency prefix, and fractional statistics
 * (p-values, rates, lifts) keep enough precision to stay meaningful.
 */
function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.map((v) => formatValue(key, v)).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value !== 'number') return String(value)

  const k = key.toLowerCase()
  // Deliberately does not match a bare "value" — `p_value` is a statistic, not money.
  const isMoney = /revenue|aov|gmv|cost|profit|price|order_value|spend/.test(k)
  const isSmallStat = Math.abs(value) < 1 && value !== 0

  const digits = isSmallStat ? 4 : 2
  const body = Number.isInteger(value)
    ? value.toLocaleString('en-US')
    : value.toLocaleString('en-US', {
        minimumFractionDigits: isSmallStat ? 4 : 0,
        maximumFractionDigits: digits,
      })

  return isMoney ? `$${body}` : body
}

/**
 * Flags the card when the backend reports a problem, so a detected SRM or a
 * breached guardrail is visually distinct from a healthy result rather than
 * reading as just another metric grid.
 */
function isAlertPayload(payload: Record<string, unknown>): boolean {
  return Object.entries(payload).some(([k, v]) => {
    const key = k.toLowerCase()
    if (v === true && /^(has|is)_/.test(key) && !/healthy|balanced|safe|valid/.test(key)) {
      return true
    }
    if (v === true && /detected|degraded|breach|violation|significant_drop/.test(key)) {
      return true
    }
    if (key === 'severity' && typeof v === 'string') {
      return /^(warning|critical|high|severe)$/i.test(v.trim())
    }
    return false
  })
}

/**
 * Renders a backend UIArtifact as a readable card.
 *
 * Two shapes reach here. A chart artifact carries a `chart_spec` and is drawn by
 * `ArtifactChart`; everything else (stat_results_card, srm_alert_card,
 * growth_prediction_card, experiment_brief, sql_result_card, …) is a flat dict
 * of computed values plus a `summary` string, which one generic metric-grid
 * presentation covers. Unmatched types previously fell through to a raw
 * `JSON.stringify` dump, which is what surfaced in chat as a black code block
 * full of unformatted numbers.
 */
export const ArtifactCardRenderer: React.FC<{ card: UIArtifactCard }> = ({ card }) => {
  const payload = (card.payload || {}) as Record<string, unknown>
  const chart = isChartArtifact(card) ? (payload.chart_spec as ChartSpec) : null
  const chartSummary = typeof payload.summary === 'string' ? payload.summary : undefined

  const summaryEntries = chart
    ? []
    : Object.entries(payload).filter(
        ([k, v]) => SUMMARY_KEYS.includes(k.toLowerCase()) && typeof v === 'string',
      )
  const metricEntries = chart
    ? []
    : Object.entries(payload).filter(
        ([k, v]) =>
          !SUMMARY_KEYS.includes(k.toLowerCase()) &&
          v !== null &&
          v !== undefined &&
          typeof v !== 'object',
      )

  const isAlert = !chart && isAlertPayload(payload)

  return (
    <article
      className={`rounded-[8px] border px-3 py-2.5 ${
        isAlert
          ? 'border-red-500/30 bg-red-500/[0.04]'
          : 'border-border-muted/20 bg-surface-base/70'
      }`}
    >
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold text-text-primary">{card.title}</h4>
        {isAlert ? (
          <span className="rounded-[6px] bg-red-500/12 px-1.5 py-0.5 text-micro font-medium text-red-700">
            Attention
          </span>
        ) : null}
      </header>

      {chart ? <ArtifactChart spec={chart} summary={chartSummary} /> : null}

      {metricEntries.length > 0 ? (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
          {metricEntries.map(([key, value]) => (
            <div key={key} className="min-w-0">
              <dt className="type-overline truncate" title={humanizeKey(key)}>
                {humanizeKey(key)}
              </dt>
              <dd className="text-xs font-medium tabular-nums text-text-primary">
                {formatValue(key, value)}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {summaryEntries.map(([key, value]) => (
        <p
          key={key}
          className={`text-xs leading-relaxed text-text-secondary ${
            metricEntries.length > 0 ? 'mt-2.5 border-t border-border-muted/10 pt-2' : ''
          }`}
        >
          {value as string}
        </p>
      ))}
    </article>
  )
}

/** The artifact cards attached to one assistant turn, stacked under its text. */
export function ArtifactCardList({ artifacts }: { artifacts: UIArtifactCard[] }) {
  if (!artifacts.length) return null
  return (
    <div className="mt-2 flex flex-col gap-2">
      {artifacts.map((card, index) => (
        <ArtifactCardRenderer key={`${card.artifact_id}-${index}`} card={card} />
      ))}
    </div>
  )
}
