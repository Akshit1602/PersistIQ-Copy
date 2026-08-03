import { useState } from 'react'
import { ArrowLeft, Plus, Search } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { ChatHistoryTree } from './ChatHistoryTree'

export function StaticSidebar() {
  const {
    openHypothesisValidator,
    goHome,
  } = useMatchView()
  const [searchQuery, setSearchQuery] = useState('')

  return (
    <aside className="history-panel flex w-[280px] shrink-0 flex-col">
      <div className="border-b border-rail-border/20 p-3">
        <button
          type="button"
          onClick={goHome}
          className="focus-ring-rail mb-2 flex w-full items-center gap-1.5 rounded-xs px-1.5 py-1 text-xs font-medium text-rail-text-secondary transition-colors hover:bg-rail-hover hover:text-rail-text-primary"
        >
          <AppIcon icon={ArrowLeft} size="xs" />
          Home Dashboard
        </button>
        <p className="mb-2 px-1.5 text-xs font-bold uppercase tracking-wider text-rail-text-primary">
          Workspaces
        </p>
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
            placeholder="Search threads..."
            className="focus-ring-rail w-full rounded-xs border border-rail-border/25 bg-rail-base/50 py-1.5 pl-10 pr-2.5 text-xs text-rail-text-primary placeholder:text-rail-text-secondary/80"
            aria-label="Search threads"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5">
        <ChatHistoryTree searchQuery={searchQuery} />
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
