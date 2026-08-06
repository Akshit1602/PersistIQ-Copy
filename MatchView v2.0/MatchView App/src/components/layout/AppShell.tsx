import { GlobalRail } from './GlobalRail'
import { StaticSidebar } from './StaticSidebar'
import { MainWorkspace } from './MainWorkspace'
import { ProjectsHome } from '../workspace/ProjectsHome'
import { HypothesisValidatorPanel } from '../workspace/HypothesisValidatorPanel'
import { AudienceSelectionWizard } from '../workspace/AudienceSelectionWizard'
import { StorePanelMatchingWizard } from '../workspace/StorePanelMatchingWizard'
import { NewProjectPanel } from '../workspace/NewProjectPanel'
import { ExperimentDataSourcesDialog } from '../workspace/ExperimentDataSourcesDialog'
import { KnowledgeArchiveView } from './KnowledgeArchiveView'
import { useMatchView } from '../../context/MatchViewContext'

export function AppShell() {
  const { selectedProjectId, selectedExperiment, experimentProjectIds, projects } = useMatchView()
  const onHome = selectedProjectId === null

  const activeExperimentProjectId = experimentProjectIds[selectedExperiment] ?? selectedProjectId
  const channel = projects.find((p) => p.id === activeExperimentProjectId)?.channel ?? 'digital'

  return (
    <div className="canvas-bg flex h-screen flex-col">
      <div className="relative flex min-h-0 flex-1">
        <div className="w-16 shrink-0" aria-hidden="true" />
        {!onHome && <StaticSidebar />}
        {onHome ? <ProjectsHome /> : <MainWorkspace />}
        <GlobalRail />
      </div>
      <NewProjectPanel />
      <HypothesisValidatorPanel />
      {channel === 'store' ? <StorePanelMatchingWizard /> : <AudienceSelectionWizard />}
      <ExperimentDataSourcesDialog />
      <KnowledgeArchiveView />
    </div>
  )
}
