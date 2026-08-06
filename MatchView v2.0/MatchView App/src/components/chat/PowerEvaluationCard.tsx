import { useId } from 'react'
import type { PowerCurveEvaluationPayload } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'
import { ArrowUpRight } from 'lucide-react'

const CHART_WIDTH = 320
const CHART_HEIGHT = 140
const PAD = { top: 12, right: 12, bottom: 28, left: 36 }

interface PowerEvaluationCardProps {
  evaluation: PowerCurveEvaluationPayload
  onOpenInsights: () => void
}

function formatAlpha(alpha: number | string): string {
  const n = typeof alpha === 'string' ? parseFloat(alpha) : alpha
  return Number.isNaN(n) ? String(alpha) : n.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')
}

export function PowerEvaluationCard({ evaluation, onOpenInsights }: PowerEvaluationCardProps) {
  const gradientId = useId().replace(/:/g, '')
  const plotW = CHART_WIDTH - PAD.left - PAD.right
  const plotH = CHART_HEIGHT - PAD.top - PAD.bottom

  const sizes = evaluation.curvePoints.map((p) => p.sampleSize)
  const minSize = Math.min(...sizes)
  const maxSize = Math.max(...sizes)
  const sizeRange = maxSize - minSize || 1

  const toX = (n: number) => PAD.left + ((n - minSize) / sizeRange) * plotW
  const toY = (power: number) => PAD.top + plotH - power * plotH

  const pathD = evaluation.curvePoints
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(p.sampleSize).toFixed(1)} ${toY(p.power).toFixed(1)}`)
    .join(' ')

  const anchorX = toX(evaluation.targetSampleSize)
  const anchorY = toY(evaluation.achievedPower)
  const areaD = `${pathD} L ${toX(maxSize).toFixed(1)} ${(PAD.top + plotH).toFixed(1)} L ${toX(minSize).toFixed(1)} ${(PAD.top + plotH).toFixed(1)} Z`

  const powerPct = (evaluation.achievedPower * 100).toFixed(0)

  return (
    <div className="flex w-full min-w-0 flex-col gap-2">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <p className="text-lg font-semibold tabular-nums leading-none tracking-tight text-text-primary">
          n = {evaluation.targetSampleSize.toLocaleString()}
        </p>
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-md bg-surface-hover px-2 py-0.5 text-xs tabular-nums text-text-secondary">
            {powerPct}% power
          </span>
          <span className="rounded-md bg-surface-hover px-2 py-0.5 text-xs tabular-nums text-text-secondary">
            α = {formatAlpha(evaluation.alpha)}
          </span>
          <span className="rounded-md bg-surface-hover px-2 py-0.5 text-xs tabular-nums text-text-secondary">
            MDE {evaluation.mde}%
          </span>
        </div>
      </div>

      <div
        className="w-full overflow-hidden rounded-xs border border-border-muted/12 bg-surface-base/60"
        style={{ height: CHART_HEIGHT }}
      >
        <svg
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          width="100%"
          height={CHART_HEIGHT}
          preserveAspectRatio="xMidYMid meet"
          className="block text-text-secondary"
          aria-label={`Power curve targeting sample size ${evaluation.targetSampleSize}`}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-border-muted)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--color-border-muted)" stopOpacity="0" />
            </linearGradient>
          </defs>

          {[0.5, 1].map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                y1={toY(tick)}
                x2={PAD.left + plotW}
                y2={toY(tick)}
                stroke="currentColor"
                strokeOpacity={0.07}
              />
              <text
                x={PAD.left - 5}
                y={toY(tick) + 3}
                textAnchor="end"
                className="fill-text-secondary text-[8px]"
              >
                {(tick * 100).toFixed(0)}%
              </text>
            </g>
          ))}

          <path d={areaD} fill={`url(#${gradientId})`} />
          <path
            d={pathD}
            fill="none"
            stroke="var(--color-border-muted)"
            strokeWidth={1.75}
            strokeLinecap="round"
          />

          <circle
            cx={anchorX}
            cy={anchorY}
            r={5}
            fill="var(--color-border-muted)"
            stroke="var(--color-surface-base, white)"
            strokeWidth={1.5}
          />

          <text
            x={PAD.left + plotW / 2}
            y={CHART_HEIGHT - 6}
            textAnchor="middle"
            className="fill-text-secondary text-[8px]"
          >
            Sample size
          </text>
        </svg>
      </div>

      <button
        type="button"
        onClick={onOpenInsights}
        className="focus-ring group flex w-fit items-center gap-1 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
      >
        View full matrix in Insights
        <AppIcon
          icon={ArrowUpRight}
          size="xs"
          className="transition-transform group-hover:-translate-y-px group-hover:translate-x-px"
        />
      </button>
    </div>
  )
}
