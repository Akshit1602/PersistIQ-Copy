import { Sparkles } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'

interface CopilotButtonProps {
  chartId: string
}

export function CopilotButton({ chartId }: CopilotButtonProps) {
  const { openChartDrawer } = useMatchView()

  return (
    <button
      type="button"
      onClick={() => openChartDrawer(chartId)}
      className="focus-ring absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-lg bg-border-muted/15 text-border-muted transition-all duration-instant hover:bg-border-muted/30 hover:shadow-glow"
      aria-label="Chart Detective AI analysis"
      title="Chart Detective"
    >
      <AppIcon icon={Sparkles} size="sm" />
    </button>
  )
}
