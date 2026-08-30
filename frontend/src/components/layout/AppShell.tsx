import { GlobalRail } from './GlobalRail'
import { StaticSidebar } from './StaticSidebar'
import { MainWorkspace } from './MainWorkspace'
import { ProjectsHome } from '../workspace/ProjectsHome'
import { HypothesisValidatorPanel } from '../workspace/HypothesisValidatorPanel'
import { AudienceSelectionWizard } from '../workspace/AudienceSelectionWizard'
import { StorePanelMatchingWizard } from '../workspace/StorePanelMatchingWizard'
import { NewProjectPanel } from '../workspace/NewProjectPanel'
import { ExperimentDataSourcesDialog } from '../workspace/ExperimentDataSourcesDialog'
import { useMatchView } from '../../context/MatchViewContext'
import { KnowledgeArchiveView } from './KnowledgeArchiveView'
import { SettingsView } from '../workspace/SettingsView'

export function AppShell() {
  const { selectedProjectId, activeGlobalPage, selectedExperiment, experimentProjectIds, projects, knowledgeArchiveOpen } =
    useMatchView()
  const onHome = selectedProjectId === null

  // Audience selection differs by channel: digital experiments pick a traffic
  // segment, store experiments match a control panel of stores. Falls back to
  // the selected project so the wizard is still correct before an experiment
  // has been chosen.
  const activeExperimentProjectId = experimentProjectIds[selectedExperiment] ?? selectedProjectId
  const channel = projects.find((p) => p.id === activeExperimentProjectId)?.channel ?? 'digital'

  return (
    <div className="canvas-bg flex h-screen flex-col">
      <div className="relative flex min-h-0 flex-1">
        <GlobalRail />
        {activeGlobalPage === 'workspace' && !onHome && !knowledgeArchiveOpen && <StaticSidebar />}
        {knowledgeArchiveOpen ? (
          <KnowledgeArchiveView />
        ) : activeGlobalPage === 'workspace' ? (
          onHome ? <ProjectsHome /> : <MainWorkspace />
        ) : (
          <SettingsView />
        )}
      </div>
      <NewProjectPanel />
      <HypothesisValidatorPanel />
      {channel === 'store' ? <StorePanelMatchingWizard /> : <AudienceSelectionWizard />}
      <ExperimentDataSourcesDialog />
    </div>
  )
}
