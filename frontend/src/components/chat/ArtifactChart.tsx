import { useId } from 'react'
import type { ChartSeriesSpec, ChartSpec } from '../../context/types'

/**
 * Renders a backend `ChartSpec` as inline SVG.
 *
 * The backend also produces Plotly JSON, but MatchView carries no charting
 * dependency and every other chart in the app is hand-drawn SVG in these same
 * tokens — a Plotly canvas dropped into a chat bubble would not match anything
 * around it. The spec is deliberately renderer-neutral for that reason: see
 * `continum/AskData/chart_spec.py`.
 */

/** Series colours by index. Kept in the app's palette rather than taking the
 * backend's `color` hint, so cards match the rest of the workspace. */
const SERIES_COLORS = ['#3b82f6', '#0d9488', '#f59e0b', '#8b5cf6', '#e11d48', '#0ea5e9']

const WIDTH = 560
const HEIGHT = 220
const MARGIN = { top: 12, right: 12, bottom: 44, left: 52 }

const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom

type ValueFormat = ChartSpec['value_format']

function formatValue(value: number, format: ValueFormat): string {
  if (!Number.isFinite(value)) return '—'
  if (format === 'currency') {
    const abs = Math.abs(value)
    if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
    if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}k`
    return `$${value.toFixed(2)}`
  }
  if (format === 'percent') {
    return Math.abs(value) <= 1 ? `${(value * 100).toFixed(2)}%` : `${value.toFixed(2)}%`
  }
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (abs < 1 && value !== 0) return value.toFixed(4)
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

/** Truncates a long category so the axis stays readable at card width. */
function truncate(label: string, max: number): string {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label
}

/**
 * Axis bounds that always include zero for bar charts — a bar whose baseline is
 * not zero exaggerates the difference between categories, which is exactly the
 * misreading these cards exist to prevent. Line charts may float, but keep a
 * padded range so a flat series does not collapse onto the axis.
 */
function computeBounds(values: number[], includeZero: boolean) {
  const finite = values.filter((v) => Number.isFinite(v))
  if (finite.length === 0) return { min: 0, max: 1 }

  let min = Math.min(...finite)
  let max = Math.max(...finite)
  if (includeZero) {
    min = Math.min(min, 0)
    max = Math.max(max, 0)
  }
  if (min === max) {
    const pad = Math.abs(min) || 1
    return { min: min - pad * 0.5, max: max + pad * 0.5 }
  }
  const pad = (max - min) * 0.08
  return { min: min - (includeZero && min >= 0 ? 0 : pad), max: max + pad }
}

function niceTicks(min: number, max: number, count = 4): number[] {
  const step = (max - min) / count
  return Array.from({ length: count + 1 }, (_, i) => min + step * i)
}

interface ChartProps {
  spec: ChartSpec
}

function seriesColor(index: number, series: ChartSeriesSpec): string {
  return SERIES_COLORS[index % SERIES_COLORS.length] ?? series.color ?? SERIES_COLORS[0]
}

function Legend({ spec }: ChartProps) {
  if (spec.series.length < 2) return null
  return (
    <ul className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
      {spec.series.map((series, index) => (
        <li key={series.name} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: seriesColor(index, series) }}
          />
          <span className="text-micro text-text-secondary">{series.name}</span>
        </li>
      ))}
    </ul>
  )
}

/** Horizontal gridlines plus the y-axis value labels. Shared by every kind. */
function Grid({ ticks, scaleY, format }: { ticks: number[]; scaleY: (v: number) => number; format: ValueFormat }) {
  return (
    <g aria-hidden="true">
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={MARGIN.left}
            x2={MARGIN.left + PLOT_WIDTH}
            y1={scaleY(tick)}
            y2={scaleY(tick)}
            stroke="currentColor"
            strokeWidth={1}
            className="text-border-muted/15"
          />
          <text
            x={MARGIN.left - 6}
            y={scaleY(tick) + 3}
            textAnchor="end"
            className="fill-text-secondary"
            style={{ fontSize: 9 }}
          >
            {formatValue(tick, format)}
          </text>
        </g>
      ))}
    </g>
  )
}

function CategoryAxis({ categories }: { categories: string[] }) {
  // Past ~12 labels they overlap; thin them evenly rather than overprinting.
  const stride = Math.ceil(categories.length / 12)
  const band = PLOT_WIDTH / Math.max(categories.length, 1)
  const maxChars = Math.max(4, Math.floor(band / 5))

  return (
    <g>
      {categories.map((label, index) =>
        index % stride === 0 ? (
          <text
            key={`${label}-${index}`}
            x={MARGIN.left + band * (index + 0.5)}
            y={MARGIN.top + PLOT_HEIGHT + 14}
            textAnchor="middle"
            className="fill-text-secondary"
            style={{ fontSize: 9 }}
          >
            {truncate(label, maxChars)}
          </text>
        ) : null,
      )}
    </g>
  )
}

function BarChart({ spec }: ChartProps) {
  const values = spec.series.flatMap((s) => s.values.filter((v): v is number => v !== null))
  const { min, max } = computeBounds(values, true)
  const scaleY = (v: number) => MARGIN.top + PLOT_HEIGHT - ((v - min) / (max - min)) * PLOT_HEIGHT
  const zeroY = scaleY(Math.max(min, Math.min(0, max)))

  const band = PLOT_WIDTH / Math.max(spec.categories.length, 1)
  const groupCount = spec.series.length
  const barWidth = Math.max(2, (band * 0.7) / groupCount)

  return (
    <>
      <Grid ticks={niceTicks(min, max)} scaleY={scaleY} format={spec.value_format} />
      {spec.series.map((series, seriesIndex) =>
        series.values.map((value, categoryIndex) => {
          if (value === null) return null
          const x =
            MARGIN.left +
            band * (categoryIndex + 0.5) -
            (barWidth * groupCount) / 2 +
            barWidth * seriesIndex
          const y = scaleY(value)
          const error = series.error?.[categoryIndex] ?? null

          return (
            <g key={`${series.name}-${categoryIndex}`}>
              <rect
                x={x}
                y={Math.min(y, zeroY)}
                width={barWidth}
                height={Math.max(1, Math.abs(zeroY - y))}
                rx={2}
                fill={seriesColor(seriesIndex, series)}
              >
                <title>{`${spec.categories[categoryIndex]} · ${series.name}: ${formatValue(value, spec.value_format)}`}</title>
              </rect>
              {error !== null && error > 0 ? (
                <g stroke={seriesColor(seriesIndex, series)} strokeWidth={1.25} opacity={0.85}>
                  <line
                    x1={x + barWidth / 2}
                    x2={x + barWidth / 2}
                    y1={scaleY(value - error)}
                    y2={scaleY(value + error)}
                  />
                  <line
                    x1={x + barWidth * 0.25}
                    x2={x + barWidth * 0.75}
                    y1={scaleY(value + error)}
                    y2={scaleY(value + error)}
                  />
                  <line
                    x1={x + barWidth * 0.25}
                    x2={x + barWidth * 0.75}
                    y1={scaleY(value - error)}
                    y2={scaleY(value - error)}
                  />
                </g>
              ) : null}
            </g>
          )
        }),
      )}
      <line
        x1={MARGIN.left}
        x2={MARGIN.left + PLOT_WIDTH}
        y1={zeroY}
        y2={zeroY}
        stroke="currentColor"
        strokeWidth={1}
        className="text-border-muted/40"
      />
      <CategoryAxis categories={spec.categories} />
    </>
  )
}

function LineChart({ spec, filled, markersOnly }: ChartProps & { filled?: boolean; markersOnly?: boolean }) {
  const values = spec.series.flatMap((s) => s.values.filter((v): v is number => v !== null))
  const { min, max } = computeBounds(values, Boolean(filled))
  const scaleY = (v: number) => MARGIN.top + PLOT_HEIGHT - ((v - min) / (max - min)) * PLOT_HEIGHT
  const count = Math.max(spec.categories.length, 1)
  const scaleX = (i: number) =>
    count === 1 ? MARGIN.left + PLOT_WIDTH / 2 : MARGIN.left + (PLOT_WIDTH / (count - 1)) * i
  const gradientId = useId()

  return (
    <>
      <Grid ticks={niceTicks(min, max)} scaleY={scaleY} format={spec.value_format} />
      {spec.series.map((series, seriesIndex) => {
        const color = seriesColor(seriesIndex, series)
        // Null values break the line rather than interpolating across a gap —
        // a straight segment over missing data invents readings that were
        // never measured.
        const segments: { x: number; y: number }[][] = []
        let current: { x: number; y: number }[] = []
        series.values.forEach((value, index) => {
          if (value === null) {
            if (current.length) segments.push(current)
            current = []
            return
          }
          current.push({ x: scaleX(index), y: scaleY(value) })
        })
        if (current.length) segments.push(current)

        return (
          <g key={series.name}>
            {filled && segments.length === 1 && segments[0].length > 1 ? (
              <>
                <defs>
                  <linearGradient id={`${gradientId}-${seriesIndex}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <path
                  d={`M ${segments[0].map((p) => `${p.x} ${p.y}`).join(' L ')} L ${
                    segments[0][segments[0].length - 1].x
                  } ${MARGIN.top + PLOT_HEIGHT} L ${segments[0][0].x} ${MARGIN.top + PLOT_HEIGHT} Z`}
                  fill={`url(#${gradientId}-${seriesIndex})`}
                />
              </>
            ) : null}

            {!markersOnly
              ? segments.map((segment, i) => (
                  <path
                    key={i}
                    d={`M ${segment.map((p) => `${p.x} ${p.y}`).join(' L ')}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={1.75}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                ))
              : null}

            {series.values.map((value, index) =>
              value === null ? null : (
                <circle key={index} cx={scaleX(index)} cy={scaleY(value)} r={2.5} fill={color}>
                  <title>{`${spec.categories[index]} · ${series.name}: ${formatValue(value, spec.value_format)}`}</title>
                </circle>
              ),
            )}
          </g>
        )
      })}
      <CategoryAxis categories={spec.categories} />
    </>
  )
}

interface PieWedge {
  label: string
  value: number
  start: number
  end: number
}

function PieChart({ spec }: ChartProps) {
  const series = spec.series[0]
  const slices = spec.categories
    .map((label, index) => ({ label, value: series?.values[index] ?? null }))
    .filter((s): s is { label: string; value: number } => s.value !== null && s.value > 0)

  const total = slices.reduce((sum, s) => sum + s.value, 0)
  if (total <= 0) return null

  const cx = MARGIN.left + PLOT_WIDTH / 2
  const cy = MARGIN.top + PLOT_HEIGHT / 2
  const radius = Math.min(PLOT_WIDTH, PLOT_HEIGHT) / 2 - 4

  // Angles are accumulated into the result itself rather than through a running
  // variable: reassigning one during render makes the output depend on render
  // order, which React's rules of immutability forbid.
  const wedges = slices.reduce<PieWedge[]>((acc, slice) => {
    const start = acc.length > 0 ? acc[acc.length - 1].end : -Math.PI / 2
    const sweep = (slice.value / total) * Math.PI * 2
    return [...acc, { ...slice, start, end: start + sweep }]
  }, [])

  return (
    <g>
      {wedges.map((slice, index) => {
        const { start, end } = slice

        const x1 = cx + radius * Math.cos(start)
        const y1 = cy + radius * Math.sin(start)
        const x2 = cx + radius * Math.cos(end)
        const y2 = cy + radius * Math.sin(end)
        const largeArc = end - start > Math.PI ? 1 : 0

        // A single slice covering the whole circle has coincident endpoints,
        // which collapses an arc path to nothing — draw the circle instead.
        const path =
          wedges.length === 1
            ? null
            : `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`

        const color = SERIES_COLORS[index % SERIES_COLORS.length]
        const label = `${slice.label}: ${formatValue(slice.value, spec.value_format)} (${(
          (slice.value / total) *
          100
        ).toFixed(1)}%)`

        return path ? (
          <path key={slice.label} d={path} fill={color} stroke="#ffffff" strokeWidth={1}>
            <title>{label}</title>
          </path>
        ) : (
          <circle key={slice.label} cx={cx} cy={cy} r={radius} fill={color}>
            <title>{label}</title>
          </circle>
        )
      })}
    </g>
  )
}

function PieLegend({ spec }: ChartProps) {
  const series = spec.series[0]
  if (!series) return null
  return (
    <ul className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
      {spec.categories.map((label, index) => (
        <li key={label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: SERIES_COLORS[index % SERIES_COLORS.length] }}
          />
          <span className="text-micro text-text-secondary">
            {label}
            {series.values[index] !== null
              ? ` · ${formatValue(series.values[index] as number, spec.value_format)}`
              : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function ArtifactChart({ spec, summary }: { spec: ChartSpec; summary?: string }) {
  const hasData = spec.series.some((s) => s.values.some((v) => v !== null))
  if (!spec.categories.length || !hasData) {
    return (
      <p className="text-xs text-text-secondary">
        {summary || 'No chartable data was returned for this request.'}
      </p>
    )
  }

  const isPie = spec.kind === 'pie'

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label={summary || spec.title}
        preserveAspectRatio="xMidYMid meet"
      >
        {spec.kind === 'line' ? <LineChart spec={spec} /> : null}
        {spec.kind === 'area' ? <LineChart spec={spec} filled /> : null}
        {spec.kind === 'scatter' ? <LineChart spec={spec} markersOnly /> : null}
        {spec.kind === 'bar' || spec.kind === 'grouped_bar' ? <BarChart spec={spec} /> : null}
        {isPie ? <PieChart spec={spec} /> : null}

        {spec.y_title && !isPie ? (
          <text
            transform={`translate(11 ${MARGIN.top + PLOT_HEIGHT / 2}) rotate(-90)`}
            textAnchor="middle"
            className="fill-text-secondary"
            style={{ fontSize: 9 }}
          >
            {truncate(spec.y_title, 26)}
          </text>
        ) : null}
        {spec.x_title && !isPie ? (
          <text
            x={MARGIN.left + PLOT_WIDTH / 2}
            y={HEIGHT - 6}
            textAnchor="middle"
            className="fill-text-secondary"
            style={{ fontSize: 9 }}
          >
            {truncate(spec.x_title, 40)}
          </text>
        ) : null}
      </svg>

      {isPie ? <PieLegend spec={spec} /> : <Legend spec={spec} />}

      {spec.notes.length > 0 ? (
        <figcaption className="mt-1.5 text-micro leading-relaxed text-text-secondary">
          {spec.notes.join(' ')}
        </figcaption>
      ) : null}
    </figure>
  )
}
