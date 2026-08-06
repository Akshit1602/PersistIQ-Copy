import { useMatchView } from '../../context/MatchViewContext'
import { AnalyticsLabPanel } from '../analytics-lab/AnalyticsLabPanel'
import { ChatView } from '../workspace/ChatView'
import { InsightsView } from '../workspace/InsightsView'
import { ReportsView } from '../workspace/ReportsView'
import { WorkspaceHeader } from '../workspace/WorkspaceHeader'

export function MainWorkspace() {
  const { currentTab, currentPersona } = useMatchView()

  return (
    <main className="flex min-w-0 flex-1 overflow-hidden bg-surface-base">
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <WorkspaceHeader />
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {currentTab === 'chat' && <ChatView />}
          {currentTab === 'insights' && <InsightsView />}
          {currentTab === 'reports' && <ReportsView />}
        </div>
      </div>
      {currentPersona === 'analyst' && <AnalyticsLabPanel />}
    </main>
  )
}
