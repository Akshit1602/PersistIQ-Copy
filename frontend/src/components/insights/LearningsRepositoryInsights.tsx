import { BookOpen, Hash } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import { PAST_EXPERIMENTS_DB } from '../../data/storeCausalRoi'

export function LearningsRepositoryInsights() {
  const records = PAST_EXPERIMENTS_DB
  const avgLift = records.reduce((s, r) => s + r.netLiftPercent, 0) / records.length
  const avgIroas = records.reduce((s, r) => s + r.iroas, 0) / records.length

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <AppIcon icon={BookOpen} size="sm" className="text-border-muted" />
          <p className="text-sm font-semibold text-text-primary">Meta-Analysis Summary</p>
        </div>
        <p className="text-xs text-text-secondary leading-relaxed">
          Across {records.length} past store pilots, average net lift was{' '}
          <strong className="text-text-primary">{avgLift >= 0 ? '+' : ''}{avgLift.toFixed(2)}%</strong> with a{' '}
          <strong className="text-text-primary">{avgIroas.toFixed(1)}x</strong> average iROAS.
        </p>
      </div>

      <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-4 py-3 overflow-x-auto">
        <p className="type-overline mb-2">Searchable Experiment Database</p>
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-text-secondary">
              <th className="pr-3 py-1">Initiative</th>
              <th className="pr-3 py-1">Archetype</th>
              <th className="pr-3 py-1">Net Lift</th>
              <th className="pr-3 py-1">iROAS</th>
              <th className="pr-3 py-1">Completed</th>
              <th className="py-1">Pre-Registration Hash</th>
            </tr>
          </thead>
          <tbody>
            {records.map((e) => (
              <tr key={e.name} className="border-t border-border-muted/10">
                <td className="pr-3 py-1.5 text-text-primary">{e.name}</td>
                <td className="pr-3 py-1.5">
                  <span className="rounded-xs bg-surface-hover px-1.5 py-0.5 text-micro text-text-secondary">{e.archetype}</span>
                </td>
                <td className={`pr-3 py-1.5 tabular-nums font-medium ${e.netLiftPercent >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                  {e.netLiftPercent >= 0 ? '+' : ''}{e.netLiftPercent.toFixed(1)}%
                </td>
                <td className="pr-3 py-1.5 tabular-nums">{e.iroas.toFixed(1)}x</td>
                <td className="pr-3 py-1.5 text-text-secondary">{e.dateCompleted}</td>
                <td className="py-1.5">
                  <span className="flex items-center gap-1 font-mono text-micro text-text-secondary" title="Frozen SHA-256 design hash from pre-registration">
                    <AppIcon icon={Hash} size="xs" /> {e.designHash}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
