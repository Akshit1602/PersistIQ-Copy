import { ArrowUpRight, Check, ListFilter, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMatchView } from '../../context/MatchViewContext'
import type { ModuleId } from '../../context/types'
import { getModuleIcon } from '../../data/moduleIcons'
import { MODULE_BY_ID } from '../../data/moduleRegistry'
import { ChatRichText } from '../chat/ChatRichText'
import { ArtifactCardList } from '../chat/ArtifactCard'
import { DownloadAsMenu } from '../shared/DownloadAsMenu'
import { AppIcon } from '../shared/AppIcon'
import { Sparkles } from 'lucide-react'

/** Copilot reports have no Analytics Lab module, so they filter under their own
 * bucket rather than being hidden by every module filter. */
const COPILOT_FILTER = 'copilot'

type ReportFilter = 'all' | ModuleId | typeof COPILOT_FILTER

export function ReportsView() {
  const { chatReports, selectedExperiment, openReport, setTab } = useMatchView()
  const [searchQuery, setSearchQuery] = useState('')
  const [filter, setFilter] = useState<ReportFilter>('all')
  const [filterOpen, setFilterOpen] = useState(false)
  const toolbarRef = useRef<HTMLDivElement>(null)

  const experimentReports = useMemo(
    () =>
      chatReports
        .filter((r) => r.experiment === selectedExperiment)
        .sort((a, b) => b.completedAt.localeCompare(a.completedAt)),
    [chatReports, selectedExperiment],
  )

  const filterOptions = useMemo(() => {
    const ids = [...new Set(experimentReports.map((r) => r.moduleId).filter(Boolean))] as ModuleId[]
    const hasUnmapped = experimentReports.some((r) => !r.moduleId)
    return [
      { value: 'all' as ReportFilter, label: 'All types' },
      ...ids.map((id) => ({
        value: id as ReportFilter,
        label: MODULE_BY_ID[id]?.label ?? id,
      })),
      ...(hasUnmapped ? [{ value: COPILOT_FILTER as ReportFilter, label: 'Copilot' }] : []),
    ]
  }, [experimentReports])

  useEffect(() => {
    setSearchQuery('')
    setFilter('all')
    setFilterOpen(false)
  }, [selectedExperiment])

  useEffect(() => {
    if (filter !== 'all' && !filterOptions.some((o) => o.value === filter)) {
      setFilter('all')
    }
  }, [filter, filterOptions])

  useEffect(() => {
    if (!filterOpen) return
    const onPointer = (e: MouseEvent) => {
      if (!toolbarRef.current?.contains(e.target as Node)) setFilterOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFilterOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [filterOpen])

  const reports = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return experimentReports.filter((r) => {
      if (filter === COPILOT_FILTER) {
        if (r.moduleId) return false
      } else if (filter !== 'all' && r.moduleId !== filter) {
        return false
      }
      if (!q) return true
      const modLabel = (r.moduleId ? MODULE_BY_ID[r.moduleId]?.label : 'Copilot') ?? ''
      const body = r.evaluation?.summary ?? r.summary
      return (
        r.title.toLowerCase().includes(q) ||
        r.summary.toLowerCase().includes(q) ||
        body.toLowerCase().includes(q) ||
        modLabel.toLowerCase().includes(q) ||
        r.completedAt.toLowerCase().includes(q)
      )
    })
  }, [experimentReports, filter, searchQuery])

  const hasAnyReports = experimentReports.length > 0
  const filterActive = filter !== 'all'

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-4 border-b border-border-muted/12 px-5 py-3">
        <div className="min-w-0">
          <h2 className="type-title">Reports</h2>
          <p className="type-subtitle mt-0.5 truncate">
            Analytical outputs generated from chat for {selectedExperiment}
          </p>
        </div>

        {hasAnyReports ? (
          <div ref={toolbarRef} className="flex shrink-0 items-center gap-2">
            <div className="relative w-[200px] max-w-[40vw]">
              <span className="pointer-events-none absolute inset-y-0 left-0 flex w-9 items-center justify-center text-text-secondary">
                <AppIcon icon={Search} size="xs" />
              </span>
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search reports…"
                className="focus-ring w-full rounded-[8px] border border-border-muted/25 bg-surface-base py-1.5 pl-9 pr-2.5 text-xs text-text-primary placeholder:text-text-secondary"
                aria-label="Search reports"
              />
            </div>

            <div className="relative">
              <button
                type="button"
                onClick={() => setFilterOpen((o) => !o)}
                className={`focus-ring flex h-9 w-9 items-center justify-center rounded-[8px] border transition-colors ${
                  filterOpen || filterActive
                    ? 'border-border-muted/40 bg-border-muted/10 text-border-muted'
                    : 'border-border-muted/25 bg-surface-base text-text-secondary hover:border-border-muted/40 hover:text-text-primary'
                }`}
                aria-label="Filter reports"
                aria-expanded={filterOpen}
                aria-haspopup="menu"
                title="Filter"
              >
                <AppIcon icon={ListFilter} size="xs" />
              </button>
              {filterOpen ? (
                <div
                  role="menu"
                  className="absolute right-0 top-full z-20 mt-1 min-w-[180px] rounded-[8px] border border-border-muted/20 bg-surface-raised py-1 shadow-[0_8px_24px_rgba(15,23,42,0.12)]"
                >
                  {filterOptions.map((opt) => {
                    const active = filter === opt.value
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        role="menuitemradio"
                        aria-checked={active}
                        onClick={() => {
                          setFilter(opt.value)
                          setFilterOpen(false)
                        }}
                        className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-surface-hover ${
                          active ? 'font-medium text-text-primary' : 'text-text-secondary'
                        }`}
                      >
                        <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
                          {active ? <AppIcon icon={Check} size="xs" /> : null}
                        </span>
                        {opt.label}
                      </button>
                    )
                  })}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {!hasAnyReports ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-sm font-medium text-text-primary">No reports yet</p>
            <p className="mt-1 max-w-xs text-xs text-text-secondary">
              Complete Initiative Setup & Benchmarking or run a module — outputs are saved here automatically.
            </p>
            <button
              type="button"
              onClick={() => setTab('chat')}
              className="focus-ring mt-4 rounded-[8px] border border-border-muted/30 px-3 py-1.5 text-xs font-medium text-text-secondary hover:border-border-muted hover:text-text-primary"
            >
              Go to Chat
            </button>
          </div>
        ) : reports.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-sm font-medium text-text-primary">No matching reports</p>
            <p className="mt-1 max-w-xs text-xs text-text-secondary">
              Try a different search term or clear the type filter.
            </p>
            <button
              type="button"
              onClick={() => {
                setSearchQuery('')
                setFilter('all')
              }}
              className="focus-ring mt-4 rounded-[8px] border border-border-muted/30 px-3 py-1.5 text-xs font-medium text-text-secondary hover:border-border-muted hover:text-text-primary"
            >
              Clear search & filter
            </button>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {reports.map((report) => {
              const mod = report.moduleId ? MODULE_BY_ID[report.moduleId] : undefined
              const ModIcon = report.moduleId ? getModuleIcon(report.moduleId) : Sparkles
              const isBrief = report.moduleId === 'brief-generator'
              const fullBody = report.evaluation?.summary ?? report.summary
              const artifacts = report.artifacts ?? []
              // A report whose charts are already on the card has nothing more
              // to open elsewhere.
              const canOpenInInsights = Boolean(report.moduleId) && artifacts.length === 0

              return (
                <li key={report.id}>
                  <article className="glass-panel rounded-[8px] px-3.5 py-3">
                    <div className="flex items-start gap-2.5">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-surface-hover">
                        <AppIcon icon={ModIcon} size="sm" className="text-border-muted" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                          <h3 className="text-xs font-semibold text-text-primary">{report.title}</h3>
                          <span className="text-micro tabular-nums text-text-secondary">
                            {report.duration}
                          </span>
                        </div>
                        <p className="mt-1 text-micro text-text-secondary">
                          {mod?.label ?? 'Copilot'} · {report.completedAt}
                        </p>
                      </div>
                    </div>

                    <div className="mt-2.5 max-h-48 overflow-y-auto overflow-x-hidden rounded-[8px] border border-border-muted/10 bg-surface-base/70 px-3 py-2.5">
                      <ChatRichText content={fullBody} />
                    </div>

                    <ArtifactCardList artifacts={artifacts} />

                    <div className="mt-2.5 flex items-center justify-end gap-2">
                      {isBrief ? (
                        <DownloadAsMenu filename={report.title} markdown={fullBody} />
                      ) : canOpenInInsights ? (
                        <button
                          type="button"
                          onClick={() => openReport(report.id)}
                          className="focus-ring inline-flex items-center gap-1 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
                        >
                          Open in Insights
                          <AppIcon icon={ArrowUpRight} size="xs" />
                        </button>
                      ) : null}
                    </div>
                  </article>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
