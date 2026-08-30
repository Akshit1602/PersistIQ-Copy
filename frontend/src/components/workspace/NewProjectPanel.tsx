import { useEffect, useState, type ReactNode } from 'react'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Database,
  Globe,
  Monitor,
  Store,
  X,
} from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { ExperimentDataSourceType, ProjectChannel } from '../../context/types'
import { AppIcon } from '../shared/AppIcon'

const PROJECT_STEPS = [
  { id: 1 as const, label: 'Details', short: 'Details' },
  { id: 2 as const, label: 'Data sources', short: 'Data' },
]

const CHANNEL_OPTIONS: {
  value: ProjectChannel
  label: string
  hint: string
  icon: typeof Monitor
}[] = [
  {
    value: 'digital',
    label: 'Digital',
    hint: 'Web, app, and online journeys',
    icon: Monitor,
  },
  {
    value: 'store',
    label: 'Store',
    hint: 'In-store and physical retail',
    icon: Store,
  },
]

function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <label className="mb-1 block text-micro font-semibold uppercase tracking-wide text-text-secondary">
      {children}
    </label>
  )
}

const inputClass =
  'focus-ring w-full rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
const textareaClass = `${inputClass} resize-none`

export function NewProjectPanel() {
  const { newProjectPanelOpen, closeNewProjectPanel, createProject } = useMatchView()
  const [step, setStep] = useState<1 | 2>(1)
  const [visible, setVisible] = useState(false)
  const [name, setName] = useState('')
  const [channel, setChannel] = useState<ProjectChannel | null>('digital')
  const [description, setDescription] = useState('')
  const [objective, setObjective] = useState('')
  const [sourceType, setSourceType] = useState<ExperimentDataSourceType>('internal')
  const [externalConnection, setExternalConnection] = useState('')

  useEffect(() => {
    if (newProjectPanelOpen) {
      setVisible(true)
      return
    }
    const t = window.setTimeout(() => setVisible(false), 220)
    return () => window.clearTimeout(t)
  }, [newProjectPanelOpen])

  useEffect(() => {
    if (!newProjectPanelOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newProjectPanelOpen])

  const step1Valid = Boolean(name.trim() && channel && description.trim())
  const step2Valid =
    sourceType === 'internal' ||
    (sourceType === 'external' && externalConnection.trim().length > 0)
  const canNext = step === 1 ? step1Valid : step2Valid

  const resetDraft = () => {
    setStep(1)
    setName('')
    setChannel('digital')
    setDescription('')
    setObjective('')
    setSourceType('internal')
    setExternalConnection('')
  }

  const handleClose = () => {
    closeNewProjectPanel()
    window.setTimeout(resetDraft, 220)
  }

  const handleCreate = () => {
    if (!step1Valid || !step2Valid || !channel) return
    createProject({
      name: name.trim(),
      description: description.trim(),
      objective: objective.trim() || undefined,
      channel,
      dataSource: {
        type: sourceType,
        externalConnection:
          sourceType === 'external' ? externalConnection.trim() || undefined : undefined,
      },
    })
    resetDraft()
  }

  if (!visible && !newProjectPanelOpen) return null

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <button
        type="button"
        className={`absolute inset-0 bg-black/30 transition-opacity duration-200 ${
          newProjectPanelOpen ? 'opacity-100' : 'opacity-0'
        }`}
        onClick={handleClose}
        aria-label="Close new project panel"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-panel-title"
        className={`relative flex h-full w-full max-w-[560px] flex-col border-l border-border-muted/20 bg-surface-raised shadow-glow transition-transform duration-200 ease-out ${
          newProjectPanelOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-muted/20 px-4 py-3.5">
          <div>
            <h2 id="new-project-panel-title" className="text-sm font-semibold text-text-primary">
              New Project
            </h2>
            <p className="mt-0.5 text-xs text-text-secondary">
              Create a folder, connect MatchView data sources, then run hypotheses inside it.
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
            aria-label="Close"
          >
            <AppIcon icon={X} size="sm" />
          </button>
        </header>

        <nav className="shrink-0 border-b border-border-muted/15 px-4 py-3" aria-label="Project steps">
          <ol className="grid grid-cols-2 gap-2">
            {PROJECT_STEPS.map((s) => {
              const done = s.id < step
              const active = s.id === step
              return (
                <li key={s.id}>
                  <div
                    className={`flex items-center gap-2 rounded-xs px-2 py-2 ${
                      active ? 'bg-border-muted/10' : ''
                    }`}
                  >
                    <span
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-micro font-semibold ${
                        done
                          ? 'bg-border-muted text-white'
                          : active
                            ? 'border border-border-muted text-border-muted'
                            : 'border border-border-muted/30 text-text-secondary'
                      }`}
                    >
                      {done ? <AppIcon icon={Check} size="xs" /> : s.id}
                    </span>
                    <span
                      className={`text-xs font-medium ${
                        active ? 'text-text-primary' : 'text-text-secondary'
                      }`}
                    >
                      {s.label}
                    </span>
                  </div>
                </li>
              )
            })}
          </ol>
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {step === 1 && (
            <div className="flex flex-col gap-3.5">
              <div>
                <FieldLabel>Project name</FieldLabel>
                <input
                  className={inputClass}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Incremental lift measurement"
                  autoFocus
                />
              </div>

              <div>
                <FieldLabel>Channel</FieldLabel>
                <div
                  className="grid grid-cols-2 gap-2"
                  role="radiogroup"
                  aria-label="Project channel"
                >
                  {CHANNEL_OPTIONS.map((opt) => {
                    const selected = channel === opt.value
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => setChannel(opt.value)}
                        className={`focus-ring flex flex-col items-start gap-2 rounded-xs border px-3 py-3 text-left transition-colors ${
                          selected
                            ? 'border-border-muted bg-border-muted text-white'
                            : 'border-border-muted/20 bg-surface-base hover:border-border-muted/40'
                        }`}
                      >
                        <span
                          className={`flex h-8 w-8 items-center justify-center rounded-xs ${
                            selected
                              ? 'bg-white/20 text-white'
                              : 'bg-surface-hover text-text-secondary'
                          }`}
                        >
                          <AppIcon icon={opt.icon} size="sm" />
                        </span>
                        <span>
                          <span
                            className={`block text-xs font-semibold ${
                              selected ? 'text-white' : 'text-text-primary'
                            }`}
                          >
                            {opt.label}
                          </span>
                          <span
                            className={`mt-0.5 block text-micro leading-snug ${
                              selected ? 'text-white/85' : 'text-text-secondary'
                            }`}
                          >
                            {opt.hint}
                          </span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div>
                <FieldLabel>Description</FieldLabel>
                <textarea
                  className={textareaClass}
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What portfolio of experiments will this project hold?"
                />
              </div>
              <div>
                <FieldLabel>Business objective (optional)</FieldLabel>
                <textarea
                  className={textareaClass}
                  rows={3}
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                  placeholder="e.g. Lift digital CVR without harming refund guardrails"
                />
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="flex flex-col gap-3">
              <p className="text-xs text-text-secondary">
                Connect MatchView to the data warehouse this project will use for baselines,
                metrics, and readouts.
              </p>
              <label className="flex cursor-pointer items-start gap-2.5 rounded-xs border border-border-muted/20 bg-surface-base p-3 transition-colors has-[:checked]:border-border-muted/40 has-[:checked]:bg-surface-hover">
                <input
                  type="radio"
                  name="project-source-type"
                  checked={sourceType === 'internal'}
                  onChange={() => setSourceType('internal')}
                  className="mt-0.5"
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
                    <AppIcon icon={Database} size="xs" />
                    Internal MatchView tables
                  </span>
                  <span className="mt-0.5 block text-xs text-text-secondary">
                    Use managed experiment tables and metrics already wired into MatchView.
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-start gap-2.5 rounded-xs border border-border-muted/20 bg-surface-base p-3 transition-colors has-[:checked]:border-border-muted/40 has-[:checked]:bg-surface-hover">
                <input
                  type="radio"
                  name="project-source-type"
                  checked={sourceType === 'external'}
                  onChange={() => setSourceType('external')}
                  className="mt-0.5"
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
                    <AppIcon icon={Globe} size="xs" />
                    External connection
                  </span>
                  <span className="mt-0.5 block text-xs text-text-secondary">
                    Point to Snowflake, BigQuery, or a custom warehouse URI.
                  </span>
                </span>
              </label>
              {sourceType === 'external' && (
                <div>
                  <FieldLabel>Connection URI</FieldLabel>
                  <input
                    className={inputClass}
                    value={externalConnection}
                    onChange={(e) => setExternalConnection(e.target.value)}
                    placeholder="snowflake://account/db/schema"
                  />
                </div>
              )}
            </div>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-border-muted/20 px-4 py-3">
          <button
            type="button"
            onClick={() => setStep(1)}
            disabled={step === 1}
            className="focus-ring inline-flex items-center gap-1 rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            <AppIcon icon={ChevronLeft} size="xs" />
            Back
          </button>
          {step === 1 ? (
            <button
              type="button"
              onClick={() => canNext && setStep(2)}
              disabled={!canNext}
              className="focus-ring inline-flex items-center gap-1 rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
              <AppIcon icon={ChevronRight} size="xs" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleCreate}
              disabled={!canNext}
              className="focus-ring rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Create Project
            </button>
          )}
        </footer>
      </aside>
    </div>
  )
}
