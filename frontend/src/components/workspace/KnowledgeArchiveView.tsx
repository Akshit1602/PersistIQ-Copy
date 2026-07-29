import { useState, useMemo } from 'react'
import { Search, Archive, Filter } from 'lucide-react'
import { AppIcon } from '../shared/AppIcon'

// Define the shape of historical learning based on the data file
export interface HistoricalLearning {
  id: string
  experiment: string
  summary: string
  keywords: string[]
  outcome: 'Ship' | 'Iterate' | 'Kill' | 'Hold'
}

// We can import LEARNINGS directly or copy it for local resilience
const LEARNINGS: HistoricalLearning[] = [
  {
    id: 'hl-1',
    experiment: 'Walmart Banner Redesign',
    summary: '+4.2% CTR lift; creative contrast drove acquisition without hurting bounce.',
    keywords: ['banner', 'ctr', 'click', 'creative', 'acquisition', 'traffic'],
    outcome: 'Ship',
  },
  {
    id: 'hl-2',
    experiment: 'Cart Flow Optimization',
    summary: 'Checkout step simplification lifted CVR; guardrail refund rate held flat.',
    keywords: ['cart', 'checkout', 'cvr', 'conversion', 'abandonment', 'flow'],
    outcome: 'Ship',
  },
  {
    id: 'hl-3',
    experiment: 'Holiday Promo Lift Test',
    summary: 'Aggressive promo copy lifted GMV but raised refund rate — iterate messaging.',
    keywords: ['promo', 'gmv', 'holiday', 'discount', 'revenue', 'refund'],
    outcome: 'Iterate',
  },
  {
    id: 'hl-4',
    experiment: 'Mobile PDP Layout v2',
    summary: 'Above-fold CTA change improved activation; session depth secondary improved.',
    keywords: ['mobile', 'pdp', 'cta', 'activation', 'engagement'],
    outcome: 'Ship',
  },
  {
    id: 'hl-5',
    experiment: 'Email Re-engagement Cadence',
    summary: 'Higher frequency hurt unsubscribe guardrail — killed weekly burst variant.',
    keywords: ['email', 'retention', 'churn', 'unsubscribe', 're-engagement'],
    outcome: 'Kill',
  },
]

export function KnowledgeArchiveView() {
  const [searchQuery, setSearchQuery] = useState('')
  const [outcomeFilter, setOutcomeFilter] = useState<'All' | 'Ship' | 'Iterate' | 'Kill' | 'Hold'>('All')

  const filteredLearnings = useMemo(() => {
    return LEARNINGS.filter((item) => {
      // 1. Filter by search query
      const query = searchQuery.toLowerCase().trim()
      const matchesSearch =
        !query ||
        item.experiment.toLowerCase().includes(query) ||
        item.summary.toLowerCase().includes(query) ||
        item.keywords.some((k) => k.toLowerCase().includes(query))

      // 2. Filter by outcome
      const matchesOutcome = outcomeFilter === 'All' || item.outcome === outcomeFilter

      return matchesSearch && matchesOutcome
    })
  }, [searchQuery, outcomeFilter])

  const getOutcomeBadgeClass = (outcome: 'Ship' | 'Iterate' | 'Kill' | 'Hold') => {
    switch (outcome) {
      case 'Ship':
        return 'bg-emerald-500/12 text-emerald-700 border-emerald-500/20'
      case 'Iterate':
        return 'bg-amber-500/12 text-amber-700 border-amber-500/20'
      case 'Kill':
        return 'bg-red-500/12 text-red-700 border-red-500/20'
      case 'Hold':
        return 'bg-slate-500/12 text-slate-700 border-slate-500/20'
      default:
        return 'bg-slate-500/12 text-slate-700 border-slate-500/20'
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface-base">
      {/* Header section */}
      <div className="flex shrink-0 items-center justify-between gap-4 border-b border-border-muted/12 px-6 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <AppIcon icon={Archive} size="sm" className="text-border-muted" />
            <h2 className="type-title">Knowledge Archive</h2>
          </div>
          <p className="type-subtitle mt-0.5">
            Historical digital experiments, outcomes, and conformed learnings repository.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {/* Search bar */}
          <div className="relative w-[240px] max-w-[40vw]">
            <span className="pointer-events-none absolute inset-y-0 left-0 flex w-9 items-center justify-center text-text-secondary">
              <AppIcon icon={Search} size="xs" />
            </span>
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search learnings by keyword..."
              className="focus-ring w-full rounded-[8px] border border-border-muted/25 bg-surface-raised py-1.5 pl-9 pr-2.5 text-xs text-text-primary placeholder:text-text-secondary"
              aria-label="Search learnings"
            />
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden p-6">
        {/* Outcome Filter Tabs */}
        <div className="mb-4 flex flex-wrap items-center gap-1.5 border-b border-border-muted/10 pb-3">
          <span className="mr-2 flex items-center gap-1 text-xs font-semibold text-text-secondary">
            <AppIcon icon={Filter} size="xs" />
            Outcome:
          </span>
          {(['All', 'Ship', 'Iterate', 'Kill', 'Hold'] as const).map((tab) => {
            const isActive = outcomeFilter === tab
            return (
              <button
                key={tab}
                type="button"
                onClick={() => setOutcomeFilter(tab)}
                className={`focus-ring rounded-xs px-3 py-1 text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-border-muted text-white shadow-glow'
                    : 'bg-surface-raised text-text-secondary hover:bg-surface-hover hover:text-text-primary'
                }`}
              >
                {tab}
              </button>
            )
          })}
        </div>

        {/* Results List */}
        <div className="flex-1 overflow-y-auto pr-1">
          {filteredLearnings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <p className="text-sm font-medium text-text-primary">No learnings found</p>
              <p className="mt-1 max-w-xs text-xs text-text-secondary">
                Try a different search term or clear the outcome filter.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSearchQuery('')
                  setOutcomeFilter('All')
                }}
                className="focus-ring mt-4 rounded-[8px] border border-border-muted/30 px-3 py-1.5 text-xs font-medium text-text-secondary hover:border-border-muted hover:text-text-primary"
              >
                Reset Filter & Search
              </button>
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {filteredLearnings.map((learning) => (
                <li key={learning.id}>
                  <article className="glass-panel h-full rounded-[8px] border border-border-muted/12 bg-surface-raised/40 p-4 hover:border-border-muted/30 transition-all">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <span className="text-micro font-bold uppercase tracking-wider text-text-secondary">
                          EXPERIMENT
                        </span>
                        <h3 className="text-sm font-bold text-text-primary truncate mt-0.5">
                          {learning.experiment}
                        </h3>
                      </div>
                      <span
                        className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${getOutcomeBadgeClass(
                          learning.outcome
                        )}`}
                      >
                        {learning.outcome}
                      </span>
                    </div>

                    <p className="mt-3 text-xs leading-relaxed text-text-primary bg-surface-base/50 border border-border-muted/5 rounded-[6px] px-3 py-2">
                      {learning.summary}
                    </p>

                    <div className="mt-3 flex flex-wrap gap-1">
                      {learning.keywords.map((word) => (
                        <span
                          key={word}
                          className="rounded-xs bg-surface-hover border border-border-muted/10 px-1.5 py-0.5 text-micro font-medium text-text-secondary"
                        >
                          #{word}
                        </span>
                      ))}
                    </div>
                  </article>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
