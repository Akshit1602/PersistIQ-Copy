import { Layers } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import type { DriverDecomposition } from '../../data/storeDriverDecomposition'

interface Props {
  title: string
  decomposition: DriverDecomposition
}

const DRIVERS: { key: keyof DriverDecomposition; label: string }[] = [
  { key: 'trafficDeltaPercent', label: 'Traffic' },
  { key: 'cvrDeltaPercent', label: 'CVR' },
  { key: 'uptDeltaPercent', label: 'UPT' },
  { key: 'aurDeltaPercent', label: 'AUR' },
]

export function DriverDecompositionCard({ title, decomposition }: Props) {
  return (
    <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <AppIcon icon={Layers} size="sm" className="text-border-muted" />
        <p className="text-sm font-semibold text-text-primary">{title}</p>
      </div>
      <p className="mb-2 text-micro text-text-secondary">
        Sales Lift = Traffic \u00D7 CVR \u00D7 UPT \u00D7 AUR
      </p>
      <div className="flex items-center gap-2 overflow-x-auto">
        {DRIVERS.map((d, i) => {
          const value = decomposition[d.key] as number
          return (
            <div key={d.key} className="flex items-center gap-2">
              <div className="rounded-xs bg-surface-hover/60 px-3 py-2 text-center">
                <p className="text-micro text-text-secondary">{d.label}</p>
                <p className={`text-sm font-bold tabular-nums ${value >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {value >= 0 ? '+' : ''}{value.toFixed(2)}%
                </p>
              </div>
              {i < DRIVERS.length - 1 && <span className="text-text-secondary">\u00D7</span>}
            </div>
          )
        })}
        <span className="text-text-secondary">=</span>
        <div className="rounded-xs bg-blue-100 px-3 py-2 text-center">
          <p className="text-micro text-blue-700">Total Sales Lift</p>
          <p className={`text-sm font-bold tabular-nums ${decomposition.totalSalesLiftPercent >= 0 ? 'text-green-700' : 'text-red-700'}`}>
            {decomposition.totalSalesLiftPercent >= 0 ? '+' : ''}{decomposition.totalSalesLiftPercent.toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  )
}
