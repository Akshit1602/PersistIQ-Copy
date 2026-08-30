interface SeriesPoint {
  x: number
  y: number
}

interface Props {
  /** Dashed line series (e.g. counterfactual / predicted baseline) */
  seriesA: SeriesPoint[]
  seriesALabel: string
  /** Solid line series (e.g. realized sales) */
  seriesB: SeriesPoint[]
  seriesBLabel: string
  /** Formats a Y value for the axis labels (e.g. "$102k") */
  formatY?: (v: number) => string
  /** Formats an X value for the axis labels (e.g. "W4") */
  formatX?: (v: number) => string
  height?: number
}

const defaultFormatY = (v: number) => Math.round(v).toLocaleString()
const defaultFormatX = (v: number) => `W${v}`

/**
 * A real, readable time-series chart — fixed pixel coordinate system (not a
 * 0-100 viewBox), with actual Y-axis gridlines/labels and X-axis week ticks,
 * not just a bare polyline with a legend underneath.
 */
export function TimeSeriesLineChart({
  seriesA,
  seriesALabel,
  seriesB,
  seriesBLabel,
  formatY = defaultFormatY,
  formatX = defaultFormatX,
  height = 180,
}: Props) {
  const width = 480
  const marginLeft = 56
  const marginRight = 12
  const marginTop = 10
  const marginBottom = 24
  const plotWidth = width - marginLeft - marginRight
  const plotHeight = height - marginTop - marginBottom

  const allPoints = [...seriesA, ...seriesB]
  const allY = allPoints.map((p) => p.y)
  const allX = allPoints.map((p) => p.x)
  const rawMaxY = Math.max(...allY, 1)
  const rawMinY = Math.min(...allY)
  const rawRange = rawMaxY - rawMinY
  // Dynamic Y-axis: scale from slightly below minimum to slightly above maximum
  // so the actual variance between lines is clearly visible
  const padding = rawRange > 0 ? rawRange * 0.15 : rawMaxY * 0.05
  const minY = rawMinY - padding
  const maxY = rawMaxY + padding
  const rangeY = Math.max(1, maxY - minY)
  const minX = Math.min(...allX, 0)
  const maxX = Math.max(...allX, 1)
  const rangeX = Math.max(1, maxX - minX)

  const toPx = (x: number) => marginLeft + ((x - minX) / rangeX) * plotWidth
  const toPy = (y: number) => marginTop + plotHeight - ((y - minY) / rangeY) * plotHeight

  const pathFor = (series: SeriesPoint[]) => series.map((p) => `${toPx(p.x)},${toPy(p.y)}`).join(' ')

  // 4 Y gridlines (including top and bottom)
  const yTicks = [0, 1, 2, 3].map((i) => minY + (rangeY * i) / 3)
  // X ticks: first, middle-ish, last (avoids overcrowding for long horizons)
  const xTickValues = Array.from(new Set([minX, Math.round(minX + rangeX / 2), maxX]))

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }}>
      {/* Y gridlines + labels */}
      {yTicks.map((v, i) => (
        <g key={i}>
          <line
            x1={marginLeft}
            x2={width - marginRight}
            y1={toPy(v)}
            y2={toPy(v)}
            stroke="#E2E8F0"
            strokeWidth={1}
          />
          <text x={marginLeft - 6} y={toPy(v)} textAnchor="end" dominantBaseline="middle" fontSize="9" fill="#64748B">
            {formatY(v)}
          </text>
        </g>
      ))}

      {/* X axis line */}
      <line x1={marginLeft} x2={width - marginRight} y1={marginTop + plotHeight} y2={marginTop + plotHeight} stroke="#CBD5E1" strokeWidth={1} />
      {xTickValues.map((v, i) => (
        <text key={i} x={toPx(v)} y={height - 6} textAnchor="middle" fontSize="9" fill="#64748B">
          {formatX(v)}
        </text>
      ))}

      {/* Series A: dashed counterfactual */}
      <polyline points={pathFor(seriesA)} fill="none" stroke="#94A3B8" strokeWidth="1.75" strokeDasharray="4,3" />
      {/* Series B: solid realized */}
      <polyline points={pathFor(seriesB)} fill="none" stroke="#16A34A" strokeWidth="1.75" />

      <title>{seriesALabel} vs. {seriesBLabel}</title>
    </svg>
  )
}
