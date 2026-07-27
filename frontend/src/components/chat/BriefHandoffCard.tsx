import { Download, FileText, Users } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { BriefHandoffChatMessage } from '../../context/types'
import { downloadMarkdownFile } from '../../data/hypothesisValidatorDraft'
import { AppIcon } from '../shared/AppIcon'

interface BriefHandoffCardProps {
  message: BriefHandoffChatMessage
}

export function BriefHandoffCard({ message }: BriefHandoffCardProps) {
  const { openReport, setTab, openAudienceWizard } = useMatchView()
  const preview =
    message.briefBody.length > 280 ? `${message.briefBody.slice(0, 280)}…` : message.briefBody

  const handleOpenReport = () => {
    openReport(message.reportId)
    setTab('reports')
  }

  const handleDownload = () => {
    const safe =
      message.briefTitle.replace(/[^\w\-]+/g, '-').replace(/^-|-$/g, '') || 'experiment-brief'
    downloadMarkdownFile(safe, message.briefBody)
  }

  return (
    <div className="glass-panel w-full max-w-[85%] rounded-sm border border-border-muted/25 px-3.5 py-3">
      <div className="flex items-start gap-2">
        <AppIcon icon={FileText} size="sm" className="mt-0.5 shrink-0 text-border-muted" />
        <div className="min-w-0 flex-1">
          <p className="text-micro font-semibold uppercase tracking-wide text-text-secondary">
            Experiment brief
          </p>
          <h3 className="mt-0.5 text-xs font-semibold text-text-primary">{message.briefTitle}</h3>
          {message.experimentType ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex rounded-xs border border-border-muted bg-border-muted px-2 py-0.5 text-micro font-semibold text-white">
                {message.experimentType}
              </span>
              {message.typeRationale ? (
                <span className="text-micro leading-snug text-text-secondary">
                  {message.typeRationale}
                </span>
              ) : null}
            </div>
          ) : null}
          <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-xs bg-surface-base/60 px-2.5 py-2 font-sans text-xs leading-relaxed text-text-secondary">
            {preview}
          </pre>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => openAudienceWizard()}
              className="focus-ring inline-flex items-center gap-1 rounded-xs bg-border-muted px-2.5 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90"
            >
              <AppIcon icon={Users} size="xs" />
              Configure Audience
            </button>
            <button
              type="button"
              onClick={handleOpenReport}
              className="focus-ring inline-flex items-center gap-1 rounded-xs border border-border-muted/30 bg-surface-raised px-2.5 py-1 text-xs font-medium text-text-primary transition-colors hover:border-border-muted hover:bg-surface-hover"
            >
              <AppIcon icon={FileText} size="xs" />
              Open report
            </button>
            <button
              type="button"
              onClick={handleDownload}
              className="focus-ring inline-flex items-center gap-1 rounded-xs border border-border-muted/30 bg-surface-raised px-2.5 py-1 text-xs font-medium text-text-primary transition-colors hover:border-border-muted hover:bg-surface-hover"
            >
              <AppIcon icon={Download} size="xs" />
              Download .md
            </button>
          </div>
          <time className="mt-2 block text-micro text-text-secondary">{message.timestamp}</time>
        </div>
      </div>
    </div>
  )
}
