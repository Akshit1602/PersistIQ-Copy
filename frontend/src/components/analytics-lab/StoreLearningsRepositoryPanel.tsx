import { useMemo, useState } from 'react'
import { BookOpen, Search, Hash } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'
import {
  type ArchetypeCategory,
  searchPastExperiments,
  metaAnalysisSummaryFor,
} from '../../data/storeCausalRoi'

const selectClass =
  'focus-ring box-border w-full min-w-0 appearance-none rounded-xs border border-border-muted/25 bg-surface-base bg-[length:12px_12px] bg-[right_0.65rem_center] bg-no-repeat px-2.5 py-1.5 pr-8 text-xs text-text-primary'
const selectChevronBg =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E\")"
const inputClass =
  'focus-ring box-border w-full min-w-0 rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'

const ARCHETYPE_OPTIONS: (ArchetypeCategory | 'all')[] = ['all', 'Labor & Staffing', 'Store Format & Remodel', 'Merchandising & Assortment', 'Pricing & Promo']

export function StoreLearningsRepositoryPanel() {
  const [archetype, setArchetype] = useState<ArchetypeCategory | 'all'>('all')
  const [query, setQuery] = useState('')

  const results = useMemo(() => searchPastExperiments(archetype, query), [archetype, query])
  const metaSummary = archetype !== 'all' ? metaAnalysisSummaryFor(archetype) : null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <div className="flex items-center gap-2 mb-1">
            <AppIcon icon={BookOpen} size="sm" className="text-border-muted" />
            <p className="text-sm font-semibold text-text-primary">Searchable Experiment Database</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select className={selectClass} style={{ backgroundImage: selectChevronBg }} value={archetype}
              onChange={(e) => setArchetype(e.target.value as ArchetypeCategory | 'all')}>
              {ARCHETYPE_OPTIONS.map((a) => (
                <option key={a} value={a}>{a === 'all' ? 'All Archetypes' : a}</option>
              ))}
            </select>
            <div className="relative">
              <AppIcon icon={Search} size="xs" className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-text-secondary" />
              <input type="text" className={`${inputClass} pl-6`} placeholder="Search by name…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
          </div>
        </div>

        {metaSummary && (
          <div className="rounded-[8px] border border-border-muted/25 bg-border-muted/5 px-3 py-3">
            <p className="type-overline mb-1">Meta-Analysis Summary</p>
            <p className="text-xs text-text-primary leading-relaxed">{metaSummary}</p>
          </div>
        )}

        <div className="overflow-hidden rounded-[8px] border border-border-muted/20">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-surface-hover/60">
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Experiment</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Archetype</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">Net Lift</th>
                <th className="px-2.5 py-1.5 font-medium text-text-secondary">iROAS</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.name} className="border-t border-border-muted/15">
                  <td className="px-2.5 py-1.5 text-text-primary">{r.name}</td>
                  <td className="px-2.5 py-1.5 text-text-secondary">{r.archetype}</td>
                  <td className={`px-2.5 py-1.5 tabular-nums ${r.netLiftPercent >= 0 ? 'text-green-700' : 'text-red-600'}`}>
                    {r.netLiftPercent >= 0 ? '+' : ''}{r.netLiftPercent}%
                  </td>
                  <td className="px-2.5 py-1.5 tabular-nums text-text-primary">{r.iroas}x</td>
                </tr>
              ))}
              {results.length === 0 && (
                <tr><td colSpan={4} className="px-2.5 py-3 text-center text-micro text-text-secondary">No matching experiments found.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="rounded-[8px] border border-border-muted/15 bg-surface-base/50 px-3 py-3">
          <div className="flex items-center gap-2">
            <AppIcon icon={Hash} size="sm" className="text-border-muted" />
            <p className="text-sm font-semibold text-text-primary">Pre-Registration Audit Link</p>
          </div>
          <p className="mt-1 text-xs text-text-secondary leading-relaxed">
            View the frozen SHA-256 design hash card generated during planning (Brief Generator) to verify
            that primary KPIs and control panels were not altered post-hoc.
          </p>
        </div>
      </div>
    </div>
  )
}
