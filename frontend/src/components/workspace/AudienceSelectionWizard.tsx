import { useEffect, useState, type ReactNode } from 'react'
import { Check, X } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'

function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <label className="type-overline mb-1 block">
      {children}
    </label>
  )
}

const inputClass =
  'focus-ring w-full rounded-xs border border-border-muted/25 bg-surface-base px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-secondary'
const textareaClass = `${inputClass} resize-none`

const SEGMENT_OPTIONS = [
  { value: 'all-web', label: 'All web traffic' },
  { value: 'mobile-app', label: 'Mobile app' },
  { value: 'new-visitors', label: 'New visitors' },
  { value: 'returning-visitors', label: 'Returning visitors' },
  { value: 'logged-in', label: 'Logged-in users' },
]

export function AudienceSelectionWizard() {
  const {
    audienceWizardOpen,
    closeAudienceWizard,
    saveAudienceSelection,
    selectedExperiment,
    moduleFormValuesByExperiment,
  } = useMatchView()

  const existing = moduleFormValuesByExperiment[selectedExperiment]?.['audience-selection']
  const [segment, setSegment] = useState('all-web')
  const [trafficPercent, setTrafficPercent] = useState(50)
  const [exclusions, setExclusions] = useState('')
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (audienceWizardOpen) {
      setSegment(typeof existing?.segment === 'string' ? existing.segment : 'all-web')
      setTrafficPercent(
        typeof existing?.trafficPercent === 'number' ? existing.trafficPercent : 50,
      )
      setExclusions(typeof existing?.exclusions === 'string' ? existing.exclusions : '')
      setVisible(true)
      return
    }
    const t = window.setTimeout(() => setVisible(false), 220)
    return () => window.clearTimeout(t)
  }, [audienceWizardOpen, existing])

  useEffect(() => {
    if (!audienceWizardOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeAudienceWizard()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [audienceWizardOpen, closeAudienceWizard])

  const canSave = trafficPercent > 0 && Boolean(segment) && Boolean(selectedExperiment)

  const handleSave = () => {
    if (!canSave) return
    saveAudienceSelection({ segment, trafficPercent, exclusions })
  }

  if (!visible && !audienceWizardOpen) return null

  return (
    <div className="fixed inset-0 z-[60] flex justify-end">
      <button
        type="button"
        className={`absolute inset-0 bg-black/30 transition-opacity duration-200 ${
          audienceWizardOpen ? 'opacity-100' : 'opacity-0'
        }`}
        onClick={closeAudienceWizard}
        aria-label="Close audience wizard"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="audience-wizard-title"
        className={`relative flex h-full w-full max-w-[640px] flex-col border-l border-border-muted/20 bg-surface-raised shadow-glow transition-transform duration-200 ease-out ${
          audienceWizardOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-muted/20 px-4 py-3.5">
          <div>
            <h2 id="audience-wizard-title" className="text-sm font-semibold text-text-primary">
              Configure Audience
            </h2>
            <p className="mt-0.5 text-xs text-text-secondary">
              Digital traffic segment for {selectedExperiment || 'this experiment'}.
            </p>
          </div>
          <button
            type="button"
            onClick={closeAudienceWizard}
            className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
            aria-label="Close"
          >
            <AppIcon icon={X} size="sm" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div className="flex flex-col gap-3.5">
            <div>
              <FieldLabel>Digital Segment</FieldLabel>
              <select
                className={inputClass}
                value={segment}
                onChange={(e) => setSegment(e.target.value)}
              >
                {SEGMENT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>Traffic Allocation (%)</FieldLabel>
              <input
                type="range"
                min={5}
                max={100}
                step={5}
                value={trafficPercent}
                onChange={(e) => setTrafficPercent(Number(e.target.value))}
                className="w-full"
              />
              <p className="mt-1 text-xs tabular-nums text-text-primary">{trafficPercent}%</p>
            </div>
            <div>
              <FieldLabel>Exclusions</FieldLabel>
              <textarea
                className={textareaClass}
                rows={3}
                value={exclusions}
                onChange={(e) => setExclusions(e.target.value)}
                placeholder="e.g. employees, QA traffic, bot filters…"
              />
            </div>
          </div>
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-border-muted/20 px-4 py-3">
          <button
            type="button"
            onClick={closeAudienceWizard}
            className="focus-ring rounded-xs border border-border-muted/25 px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-hover hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className="focus-ring inline-flex items-center gap-1 rounded-xs bg-border-muted px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <AppIcon icon={Check} size="xs" />
            Save Audience
          </button>
        </footer>
      </aside>
    </div>
  )
}
