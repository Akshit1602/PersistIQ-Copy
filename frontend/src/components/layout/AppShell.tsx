import { GlobalRail } from './GlobalRail'
import { StaticSidebar } from './StaticSidebar'
import { MainWorkspace } from './MainWorkspace'
import { ProjectsHome } from '../workspace/ProjectsHome'
import { HypothesisValidatorPanel } from '../workspace/HypothesisValidatorPanel'
import { AudienceSelectionWizard } from '../workspace/AudienceSelectionWizard'
import { NewProjectPanel } from '../workspace/NewProjectPanel'
import { ExperimentDataSourcesDialog } from '../workspace/ExperimentDataSourcesDialog'
import { useMatchView } from '../../context/MatchViewContext'
import { KnowledgeArchiveView } from '../workspace/KnowledgeArchiveView'
import { SettingsView } from '../workspace/SettingsView'

export function AppShell() {
  const { selectedProjectId, activeGlobalPage } = useMatchView()
  const onHome = selectedProjectId === null

  return (
    <div className="canvas-bg flex h-screen flex-col">
      <div className="relative flex min-h-0 flex-1">
        <GlobalRail />
        {activeGlobalPage === 'workspace' && !onHome && <StaticSidebar />}
        {activeGlobalPage === 'workspace' ? (
          onHome ? <ProjectsHome /> : <MainWorkspace />
        ) : activeGlobalPage === 'archive' ? (
          <KnowledgeArchiveView />
        ) : (
          <SettingsView />
        )}
      </div>
      <NewProjectPanel />
      <HypothesisValidatorPanel />
      <AudienceSelectionWizard />
      <ExperimentDataSourcesDialog />
    </div>
  )
}
