import { useEffect, useMemo, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  FolderTree,
  MoreVertical,
  Trash2,
} from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { ThreadGroup, Project } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'

interface ChatHistoryTreeProps {
  searchQuery: string
}

export function ChatHistoryTree({ searchQuery }: ChatHistoryTreeProps) {
  const {
    projects,
    threadGroups,
    activeThreadId,
    selectedProjectId,
    selectProject,
    selectThread,
    deleteThread,
    openExperimentDataSources,
  } = useMatchView()

  // Expanded state for Projects
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(() => {
    return new Set(selectedProjectId ? [selectedProjectId] : [])
  })

  // Expanded state for Experiments (folders)
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => {
    const group = threadGroups.find((g) => g.threads.some((t) => t.id === activeThreadId))
    return new Set(group ? [group.experiment] : [])
  })

  // Group thread groups by project
  const filteredTree = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) {
      return projects.map((p) => ({
        ...p,
        groups: threadGroups.filter((g) => g.projectId === p.id),
      }))
    }

    return projects
      .map((p) => {
        const projectMatch = p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q)
        const groupsForProject = threadGroups.filter((g) => g.projectId === p.id)

        const matchingGroups = groupsForProject
          .map((group) => {
            const folderMatch = group.experiment.toLowerCase().includes(q)
            const matchingThreads = group.threads.filter((t) => t.title.toLowerCase().includes(q))
            if (folderMatch) return group
            if (matchingThreads.length > 0) return { ...group, threads: matchingThreads }
            return null
          })
          .filter((g): g is ThreadGroup => g !== null)

        if (projectMatch) {
          return { ...p, groups: groupsForProject }
        } else if (matchingGroups.length > 0) {
          return { ...p, groups: matchingGroups }
        }
        return null
      })
      .filter((p): p is (Project & { groups: ThreadGroup[] }) => p !== null)
  }, [projects, threadGroups, searchQuery])

  const activeExperiment = threadGroups.find((g) =>
    g.threads.some((t) => t.id === activeThreadId),
  )?.experiment

  const activeProjectOfThread = threadGroups.find((g) =>
    g.threads.some((t) => t.id === activeThreadId),
  )?.projectId

  // Sync expanded projects/experiments on mount or thread switch
  useEffect(() => {
    if (activeProjectOfThread) {
      setExpandedProjects((prev) => new Set([...prev, activeProjectOfThread]))
    }
  }, [activeProjectOfThread])

  useEffect(() => {
    if (activeExperiment) {
      setExpandedFolders((prev) => new Set([...prev, activeExperiment]))
    }
  }, [activeExperiment])

  // Sync expansions when search query is typed
  useEffect(() => {
    if (searchQuery.trim()) {
      const pIds = filteredTree.map((p) => p.id)
      setExpandedProjects(new Set(pIds))

      const folderNames: string[] = []
      filteredTree.forEach((p) => {
        p.groups.forEach((g) => {
          folderNames.push(g.experiment)
        })
      })
      setExpandedFolders(new Set(folderNames))
    }
  }, [searchQuery, filteredTree])

  const toggleProject = (projectId: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev)
      if (next.has(projectId)) next.delete(projectId)
      else next.add(projectId)
      return next
    })
  }

  const toggleFolder = (experiment: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev)
      if (next.has(experiment)) next.delete(experiment)
      else next.add(experiment)
      return next
    })
  }

  const handleDeleteThread = (threadId: string, experiment: string, title: string) => {
    if (window.confirm(`Delete conversation "${title}"?`)) {
      deleteThread(threadId, experiment)
    }
  }

  if (filteredTree.length === 0) {
    return (
      <p className="px-1.5 py-4 text-center text-xs text-rail-text-secondary">
        {searchQuery.trim()
          ? 'No conversations match your search.'
          : 'No workspaces or hypotheses available.'}
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-2">
      {filteredTree.map((project) => {
        const isProjectExpanded = expandedProjects.has(project.id)
        const isProjectSelected = selectedProjectId === project.id

        return (
          <li key={project.id} className="rounded-xs border border-rail-border/10 p-1 bg-rail-base/10">
            {/* Project Header Row */}
            <div className="group/project flex items-center justify-between">
              <button
                type="button"
                onClick={() => {
                  toggleProject(project.id)
                  selectProject(project.id)
                }}
                className={`focus-ring-rail flex min-w-0 flex-1 items-center gap-1.5 rounded-xs px-1.5 py-1 text-left transition-colors duration-instant hover:bg-rail-hover ${
                  isProjectSelected ? 'text-rail-text-primary bg-rail-hover/50' : 'text-rail-text-secondary'
                }`}
                aria-expanded={isProjectExpanded}
              >
                <AppIcon
                  icon={isProjectExpanded ? ChevronDown : ChevronRight}
                  size="xs"
                  className="shrink-0 text-rail-text-secondary"
                />
                <AppIcon
                  icon={FolderTree}
                  size="xs"
                  className={`shrink-0 ${isProjectSelected ? 'text-rail-accent' : 'text-rail-text-secondary'}`}
                />
                <span className="min-w-0 flex-1 truncate text-xs font-bold">{project.name}</span>
              </button>
            </div>

            {/* Experiments (Dropdown) */}
            {isProjectExpanded && (
              <ul className="ml-2 mt-1 flex flex-col gap-1 border-l border-rail-border/15 pl-1.5">
                {project.groups.length === 0 ? (
                  <li className="px-1.5 py-2 text-micro text-rail-text-secondary">
                    No active experiments.
                  </li>
                ) : (
                  project.groups.map((group) => {
                    const isFolderExpanded = expandedFolders.has(group.experiment)
                    const hasActiveThread = group.threads.some((t) => t.id === activeThreadId)
                    const FolderIcon = isFolderExpanded ? FolderOpen : Folder

                    return (
                      <li key={group.experiment}>
                        <div className="group/folder flex items-center gap-0.5">
                          <button
                            type="button"
                            onClick={() => toggleFolder(group.experiment)}
                            className={`focus-ring-rail flex min-w-0 flex-1 items-center gap-1.5 rounded-xs px-1.5 py-1 text-left transition-colors duration-instant hover:bg-rail-hover ${
                              hasActiveThread ? 'text-rail-text-primary' : 'text-rail-text-secondary'
                            }`}
                            aria-expanded={isFolderExpanded}
                          >
                            <AppIcon
                              icon={isFolderExpanded ? ChevronDown : ChevronRight}
                              size="xs"
                              className="shrink-0 text-rail-text-secondary"
                            />
                            <AppIcon
                              icon={FolderIcon}
                              size="xs"
                              className={`shrink-0 ${hasActiveThread ? 'text-rail-accent' : 'text-rail-text-secondary'}`}
                            />
                            <span className="min-w-0 flex-1 truncate text-xs font-medium">{group.experiment}</span>
                            <span className="shrink-0 rounded-md bg-rail-base/40 px-1.5 py-0.5 text-micro tabular-nums text-rail-text-secondary">
                              {group.threads.length}
                            </span>
                          </button>
                          <button
                            type="button"
                            onClick={() => openExperimentDataSources(group.experiment)}
                            className="focus-ring-rail flex h-7 w-7 shrink-0 items-center justify-center rounded-xs text-rail-text-secondary opacity-0 transition-all hover:bg-rail-hover hover:text-rail-text-primary focus:opacity-100 group-hover/folder:opacity-100"
                            aria-label={`Configure data sources for ${group.experiment}`}
                            title="Configure data sources"
                          >
                            <AppIcon icon={MoreVertical} size="xs" />
                          </button>
                        </div>

                        {/* Threads of Experiment (Dropdown) */}
                        {isFolderExpanded && (
                          <ul className="ml-2.5 mt-0.5 flex flex-col gap-0.5 border-l border-rail-border/25 pl-2">
                            {group.threads.map((thread) => {
                              const isActive = thread.id === activeThreadId
                              return (
                                <li key={thread.id} className="group/thread">
                                  <div className="flex items-stretch gap-0.5">
                                    <button
                                      type="button"
                                      onClick={() => {
                                        selectProject(project.id)
                                        selectThread(thread.id, group.experiment)
                                      }}
                                      className={`focus-ring-rail flex min-w-0 flex-1 items-start gap-1.5 rounded-xs px-1.5 py-1 text-left transition-colors duration-instant hover:bg-rail-hover ${
                                        isActive
                                          ? 'border border-rail-border/40 bg-rail-hover text-rail-text-primary'
                                          : 'border border-transparent text-rail-text-secondary hover:text-rail-text-primary'
                                      }`}
                                    >
                                      <AppIcon
                                        icon={FileText}
                                        size="xs"
                                        className={`mt-0.5 shrink-0 ${
                                          isActive ? 'text-rail-accent' : 'text-rail-text-secondary'
                                        }`}
                                      />
                                      <span className="min-w-0 flex-1">
                                        <span
                                          className={`block truncate text-xs ${
                                            isActive ? 'font-medium text-rail-text-primary' : 'text-rail-text-primary'
                                          }`}
                                        >
                                          {thread.title}
                                        </span>
                                        <span className="block text-micro text-rail-text-secondary">
                                          {thread.timestamp}
                                        </span>
                                      </span>
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        handleDeleteThread(thread.id, group.experiment, thread.title)
                                      }
                                      className="focus-ring-rail flex w-7 shrink-0 items-center justify-center rounded-xs text-rail-text-secondary opacity-0 transition-all hover:bg-red-500/20 hover:text-red-300 focus:opacity-100 group-hover/thread:opacity-100"
                                      aria-label={`Delete ${thread.title}`}
                                      title="Delete conversation"
                                    >
                                      <AppIcon icon={Trash2} size="xs" />
                                    </button>
                                  </div>
                                </li>
                              )
                            })}
                          </ul>
                        )}
                      </li>
                    )
                  })
                )}
              </ul>
            )}
          </li>
        )
      })}
    </ul>
  )
}
