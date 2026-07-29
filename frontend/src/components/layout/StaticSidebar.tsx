import { useState } from 'react'
import { ArrowLeft, Plus, Search, ChevronDown, ChevronRight } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { ChatHistoryTree } from './ChatHistoryTree'

export function StaticSidebar() {
  const {
    openHypothesisValidator,
    goHome,
    projects,
    selectedProjectId,
    selectProject,
  } = useMatchView()
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(
    () => new Set(projects.map((p) => p.id))
  )

  return (
    <aside className="history-panel flex w-[280px] shrink-0 flex-col">
      <div className="border-b border-rail-border/20 p-3">
        <button
          type="button"
          onClick={goHome}
          className="focus-ring-rail mb-2 flex w-full items-center gap-1.5 rounded-xs px-1.5 py-1 text-xs font-medium text-rail-text-secondary transition-colors hover:bg-rail-hover hover:text-rail-text-primary"
        >
          <AppIcon icon={ArrowLeft} size="xs" />
          All projects
        </button>
        <div className="relative">
          <AppIcon
            icon={Search}
            size="xs"
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-rail-text-secondary"
          />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search hypotheses..."
            className="focus-ring-rail w-full rounded-xs border border-rail-border/25 bg-rail-base/50 py-1.5 pl-10 pr-2.5 text-xs text-rail-text-primary placeholder:text-rail-text-secondary/80"
            aria-label="Search hypotheses"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5 space-y-3">
        {projects.map((proj) => {
          const isExpanded = expandedProjects.has(proj.id)
          return (
            <div key={proj.id} className="space-y-1">
              <button
                type="button"
                onClick={() => {
                  setExpandedProjects((prev) => {
                    const next = new Set(prev)
                    if (next.has(proj.id)) next.delete(proj.id)
                    else next.add(proj.id)
                    return next
                  })
                  selectProject(proj.id)
                }}
                className={`focus-ring-rail flex w-full items-center justify-between rounded-xs px-2.5 py-2 text-left text-xs font-bold transition-colors hover:bg-rail-hover ${
                  selectedProjectId === proj.id
                    ? 'text-rail-text-primary bg-rail-hover/40 border-l-2 border-rail-accent'
                    : 'text-rail-text-secondary'
                }`}
              >
                <span className="truncate" title={proj.name}>
                  {proj.name}
                </span>
                <AppIcon
                  icon={isExpanded ? ChevronDown : ChevronRight}
                  size="xs"
                  className="shrink-0 text-rail-text-secondary ml-1"
                />
              </button>

              {isExpanded && (
                <div className="pl-1">
                  <ChatHistoryTree projectId={proj.id} searchQuery={searchQuery} />
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="border-t border-rail-border/20 p-2.5">
        <button
          type="button"
          onClick={openHypothesisValidator}
          className="focus-ring-rail flex w-full items-center justify-center gap-1.5 rounded-xs bg-rail-accent px-2.5 py-1.5 text-xs font-medium text-white shadow-glow transition-opacity duration-instant hover:opacity-90"
        >
          <AppIcon icon={Plus} size="xs" />
          Hypothesis Validator
        </button>
      </div>
    </aside>
  )
}
