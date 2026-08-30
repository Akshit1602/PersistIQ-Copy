import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUpDown,
  Check,
  ChevronRight,
  Database,
  FolderKanban,
  Globe,
  Inbox,
  ListFilter,
  Monitor,
  Plus,
  Search,
  Store,
  Trash2,
} from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { Project, ProjectChannel } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'
import { ExecutiveView } from './ExecutiveView'
import { OTHER_PLANNED_INITIATIVES, formatDateRange } from '../../data/storeConcurrencyReview'

const FIXED_CONCURRENT_INITIATIVE = OTHER_PLANNED_INITIATIVES[0]

type SortKey = 'name-asc' | 'name-desc' | 'date-newest' | 'date-oldest'
type FilterKey = 'all' | 'internal' | 'external'
type OpenMenu = 'filter' | 'sort' | null

const FILTER_OPTIONS: { value: FilterKey; label: string }[] = [
  { value: 'all', label: 'All sources' },
  { value: 'internal', label: 'Internal' },
  { value: 'external', label: 'External' },
]

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'name-asc', label: 'Name A–Z' },
  { value: 'name-desc', label: 'Name Z–A' },
  { value: 'date-newest', label: 'Newest first' },
  { value: 'date-oldest', label: 'Oldest first' },
]

function projectChannel(project: Project): ProjectChannel {
  return project.channel ?? 'digital'
}

function sortProjects(list: Project[], sort: SortKey): Project[] {
  const next = [...list]
  next.sort((a, b) => {
    switch (sort) {
      case 'name-asc':
        return a.name.localeCompare(b.name)
      case 'name-desc':
        return b.name.localeCompare(a.name)
      case 'date-oldest':
        return a.createdAt.localeCompare(b.createdAt)
      case 'date-newest':
      default:
        return b.createdAt.localeCompare(a.createdAt)
    }
  })
  return next
}

export function ProjectsHome() {
  const {
    projects,
    threadGroups,
    experimentProjectIds,
    selectProject,
    openNewProjectPanel,
    deleteProject,
  } = useMatchView()

  const [searchQuery, setSearchQuery] = useState('')
  const [filter, setFilter] = useState<FilterKey>('all')
  const [sort, setSort] = useState<SortKey>('date-newest')
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null)
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null)
  const toolbarRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!openMenu && !projectToDelete) return
    const onPointerDown = (e: MouseEvent) => {
      if (toolbarRef.current && !toolbarRef.current.contains(e.target as Node)) {
        setOpenMenu(null)
      }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpenMenu(null)
        setProjectToDelete(null)
      }
    }
    window.addEventListener('mousedown', onPointerDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onPointerDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [openMenu, projectToDelete])

  const confirmDelete = () => {
    if (!projectToDelete) return
    deleteProject(projectToDelete.id)
    setProjectToDelete(null)
  }

  const statsByProject = useMemo(() => {
    const map: Record<string, { experiments: number; threads: number }> = {}
    for (const project of projects) {
      const expCount = Object.values(experimentProjectIds).filter((id) => id === project.id).length
      const threads = threadGroups
        .filter((g) => g.projectId === project.id)
        .reduce((sum, g) => sum + g.threads.length, 0)
      map[project.id] = { experiments: expCount, threads }
    }
    return map
  }, [projects, experimentProjectIds, threadGroups])

  const filteredProjects = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    let list = projects.filter((p) => {
      if (filter === 'internal' && p.dataSource.type !== 'internal') return false
      if (filter === 'external' && p.dataSource.type !== 'external') return false
      if (!q) return true
      return (
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        (p.objective?.toLowerCase().includes(q) ?? false)
      )
    })
    return sortProjects(list, sort)
  }, [projects, searchQuery, filter, sort])

  const digitalProjects = filteredProjects.filter((p) => projectChannel(p) === 'digital')
  const storeProjects = filteredProjects.filter((p) => projectChannel(p) === 'store')

  const renderProjectCard = (project: Project) => {
    const stats = statsByProject[project.id] ?? { experiments: 0, threads: 0 }
    const isExternal = project.dataSource.type === 'external'
    return (
      <li key={project.id} className="h-full">
        <article className="glass-panel flex h-full flex-col rounded-[8px] border border-border-muted/15 p-4 transition-colors hover:border-border-muted/35">
          <div className="flex items-start gap-2.5">
            <button
              type="button"
              onClick={() => selectProject(project.id)}
              className="focus-ring flex min-w-0 flex-1 items-start gap-2.5 rounded-xs text-left"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-surface-hover">
                <AppIcon icon={FolderKanban} size="sm" className="text-border-muted" />
              </div>
              <div className="min-w-0 flex-1">
                {/* Title: always 1 line */}
                <h3 className="truncate text-sm font-semibold leading-5 text-text-primary">
                  {project.name}
                </h3>
                {/* Description: always reserve 2 lines so cards align */}
                <p className="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-text-secondary">
                  {project.description?.trim() || 'No description yet for this project.'}
                </p>
              </div>
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setProjectToDelete(project)
              }}
              className="focus-ring -mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-xs text-red-500 transition-colors hover:bg-red-50 hover:text-red-600"
              aria-label={`Delete project ${project.name}`}
              title="Delete"
            >
              <AppIcon icon={Trash2} size="xs" />
            </button>
          </div>

          <button
            type="button"
            onClick={() => selectProject(project.id)}
            className="focus-ring mt-auto flex flex-col rounded-xs pt-3 text-left"
          >
            <div className="flex min-h-6 flex-wrap items-center gap-2 text-micro text-text-secondary">
              <span className="rounded-md bg-surface-hover px-1.5 py-0.5 tabular-nums">
                {stats.experiments} experiment{stats.experiments === 1 ? '' : 's'}
              </span>
              <span className="rounded-md bg-surface-hover px-1.5 py-0.5 tabular-nums">
                {stats.threads} chat{stats.threads === 1 ? '' : 's'}
              </span>
              <span className="inline-flex items-center gap-1 rounded-md bg-surface-hover px-1.5 py-0.5">
                <AppIcon icon={isExternal ? Globe : Database} size="xs" />
                {isExternal ? 'External' : 'Internal'}
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-border-muted/15 pt-2.5">
              <span className="text-micro text-text-secondary">Created {project.createdAt}</span>
              <AppIcon icon={ChevronRight} size="sm" className="text-text-secondary" />
            </div>
          </button>
        </article>
      </li>
    )
  }

  const renderSection = (
    title: string,
    icon: typeof Monitor,
    sectionProjects: Project[],
    emptyTitle: string,
    emptySubtitle: string,
  ) => (
    <section className="mb-8 last:mb-0">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-xs bg-surface-hover text-border-muted">
          <AppIcon icon={icon} size="sm" />
        </span>
        <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
        <span className="rounded-md bg-surface-hover px-1.5 py-0.5 text-micro tabular-nums text-text-secondary">
          {sectionProjects.length}
        </span>
      </div>
      {sectionProjects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xs border border-dashed border-border-muted/20 bg-surface-raised/60 px-3 py-8 text-center">
          <AppIcon icon={Inbox} size="lg" className="mb-2 text-text-secondary/70" />
          <p className="text-sm font-bold text-text-primary">{emptyTitle}</p>
          <p className="mt-1 text-xs font-normal text-text-secondary">{emptySubtitle}</p>
        </div>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {sectionProjects.map(renderProjectCard)}
        </ul>
      )}
    </section>
  )

  return (
    <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface-base">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border-muted/15 bg-surface-raised px-6 py-4">
        <div className="min-w-0 shrink">
          <h1 className="type-title">Projects</h1>
          <p className="type-subtitle mt-0.5">
            Open a project folder to run Initiative Setup & Benchmarking and analyze experiments.
          </p>
        </div>

        <div ref={toolbarRef} className="flex shrink-0 items-center gap-2">
          <div className="relative w-[200px]">
            <span className="pointer-events-none absolute inset-y-0 left-0 flex w-[36px] items-center justify-center text-text-secondary">
              <AppIcon icon={Search} size="xs" />
            </span>
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search…"
              className="focus-ring w-full rounded-xs border border-border-muted/25 bg-surface-base py-1.5 pl-[36px] pr-2.5 text-xs text-text-primary placeholder:text-text-secondary"
              aria-label="Search projects"
            />
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={() => setOpenMenu((m) => (m === 'filter' ? null : 'filter'))}
              className={`focus-ring flex h-[36px] w-[36px] items-center justify-center rounded-xs border transition-colors ${
                openMenu === 'filter' || filter !== 'all'
                  ? 'border-border-muted/40 bg-border-muted/10 text-border-muted'
                  : 'border-border-muted/25 bg-surface-base text-text-secondary hover:border-border-muted/40 hover:text-text-primary'
              }`}
              aria-label="Filter projects"
              aria-expanded={openMenu === 'filter'}
              aria-haspopup="menu"
              title="Filter"
            >
              <AppIcon icon={ListFilter} size="xs" />
            </button>
            {openMenu === 'filter' ? (
              <div
                role="menu"
                className="absolute right-0 top-full z-20 mt-1 min-w-[160px] rounded-xs border border-border-muted/20 bg-surface-raised py-1 shadow-glow"
              >
                {FILTER_OPTIONS.map((opt) => {
                  const active = filter === opt.value
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      role="menuitemradio"
                      aria-checked={active}
                      onClick={() => {
                        setFilter(opt.value)
                        setOpenMenu(null)
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

          <div className="relative">
            <button
              type="button"
              onClick={() => setOpenMenu((m) => (m === 'sort' ? null : 'sort'))}
              className={`focus-ring flex h-[36px] w-[36px] items-center justify-center rounded-xs border transition-colors ${
                openMenu === 'sort' || sort !== 'date-newest'
                  ? 'border-border-muted/40 bg-border-muted/10 text-border-muted'
                  : 'border-border-muted/25 bg-surface-base text-text-secondary hover:border-border-muted/40 hover:text-text-primary'
              }`}
              aria-label="Sort projects"
              aria-expanded={openMenu === 'sort'}
              aria-haspopup="menu"
              title="Sort"
            >
              <AppIcon icon={ArrowUpDown} size="xs" />
            </button>
            {openMenu === 'sort' ? (
              <div
                role="menu"
                className="absolute right-0 top-full z-20 mt-1 min-w-[160px] rounded-xs border border-border-muted/20 bg-surface-raised py-1 shadow-glow"
              >
                {SORT_OPTIONS.map((opt) => {
                  const active = sort === opt.value
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      role="menuitemradio"
                      aria-checked={active}
                      onClick={() => {
                        setSort(opt.value)
                        setOpenMenu(null)
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

          <button
            type="button"
            onClick={openNewProjectPanel}
            className="focus-ring inline-flex h-[36px] shrink-0 items-center gap-1.5 rounded-xs bg-border-muted px-4 text-xs font-medium text-white transition-opacity hover:opacity-90"
          >
            <AppIcon icon={Plus} size="xs" />
            New Project
          </button>
        </div>
      </header>

      <div className="mx-6 mt-4">
        <ExecutiveView />
      </div>

      {projects.some((p) => projectChannel(p) === 'store') && (
        <div className="mx-6 mt-4 flex items-start gap-2.5 rounded-[8px] border border-amber-500/30 bg-amber-50/40 px-4 py-3">
          <AppIcon icon={Store} size="sm" className="mt-0.5 shrink-0 text-amber-700" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-amber-800">
              Concurrent Store Initiative Active: {FIXED_CONCURRENT_INITIATIVE.initiativeName}
            </p>
            <p className="mt-0.5 text-micro text-amber-800">
              {FIXED_CONCURRENT_INITIATIVE.archetype} · {formatDateRange(FIXED_CONCURRENT_INITIATIVE.startDate, FIXED_CONCURRENT_INITIATIVE.endDate)} · Checked against every store experiment's Review &amp; Concurrency step.
            </p>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6">
        {projects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <AppIcon icon={FolderKanban} size="lg" className="mb-3 text-text-secondary" />
            <p className="text-sm font-medium text-text-primary">No projects yet</p>
            <p className="mt-1 max-w-sm text-xs text-text-secondary">
              Create a project to connect MatchView to your data sources and start validating
              hypotheses.
            </p>
            <button
              type="button"
              onClick={openNewProjectPanel}
              className="focus-ring mt-4 rounded-xs border border-border-muted/30 px-3 py-1.5 text-xs font-medium text-text-secondary hover:border-border-muted hover:text-text-primary"
            >
              Create your first project
            </button>
          </div>
        ) : filteredProjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <AppIcon icon={Search} size="lg" className="mb-3 text-text-secondary" />
            <p className="text-sm font-medium text-text-primary">No matching projects</p>
            <p className="mt-1 text-xs text-text-secondary">
              Try a different search, filter, or sort.
            </p>
          </div>
        ) : (
          <>
            {renderSection(
              'Digital',
              Monitor,
              digitalProjects,
              'No Digital projects yet',
              'Create one and choose Digital as the channel.',
            )}
            {renderSection(
              'Store',
              Store,
              storeProjects,
              'No Store projects yet',
              'Create one and choose Store as the channel.',
            )}
          </>
        )}
      </div>

      {projectToDelete ? (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={() => setProjectToDelete(null)}
            aria-label="Dismiss delete confirmation"
          />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-project-title"
            aria-describedby="delete-project-desc"
            className="relative w-full max-w-sm rounded-sm border border-border-muted/20 bg-surface-raised p-5 shadow-glow"
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xs bg-red-50 text-red-500">
              <AppIcon icon={Trash2} size="sm" />
            </div>
            <h2
              id="delete-project-title"
              className="text-sm font-semibold text-text-primary"
            >
              Delete project?
            </h2>
            <p id="delete-project-desc" className="mt-1.5 text-xs leading-relaxed text-text-secondary">
              Delete &ldquo;{projectToDelete.name}&rdquo; and all nested experiments? This cannot be
              undone.
            </p>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setProjectToDelete(null)}
                className="focus-ring rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                className="focus-ring rounded-xs bg-red-500 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  )
}
