import { BarChart3, FileText, MessageCircle, type LucideIcon } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { Tab } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'
import { CriticalInsightsTicker } from './CriticalInsightsTicker'

const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'chat', label: 'Chat', icon: MessageCircle },
  { id: 'insights', label: 'Insights', icon: BarChart3 },
  { id: 'reports', label: 'Reports', icon: FileText },
]

export function WorkspaceHeader() {
  const { currentTab, setTab, chatReports, selectedExperiment } = useMatchView()

  const reportCount = chatReports.filter((r) => r.experiment === selectedExperiment).length

  return (
    <header className="flex shrink-0 items-center gap-3 overflow-hidden border-b border-border-muted/15 bg-surface-raised px-4 py-2">
      <CriticalInsightsTicker />

      <div
        className="flex shrink-0 rounded-xs border border-border-muted/25 bg-surface-base p-0.5"
        role="tablist"
        aria-label="Workspace view"
      >
        {TABS.map((tab) => {
          const isActive = currentTab === tab.id
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setTab(tab.id)}
              className={`focus-ring flex items-center gap-1.5 rounded-xs px-2.5 py-1 text-xs font-medium transition-all duration-instant ${
                isActive
                  ? 'bg-border-muted text-white shadow-glow'
                  : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
              }`}
            >
              <AppIcon icon={tab.icon} size="xs" />
              {tab.label}
              {tab.id === 'reports' && reportCount > 0 && (
                <span
                  className={`rounded-md px-1 text-micro tabular-nums ${
                    isActive ? 'bg-white/20' : 'bg-surface-hover'
                  }`}
                >
                  {reportCount}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </header>
  )
}
