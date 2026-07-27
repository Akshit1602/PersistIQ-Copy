import matchViewLogo from '../../assets/matchview_logo.svg'

interface MatchViewLogoProps {
  className?: string
  showWordmark?: boolean
  variant?: 'default' | 'rail'
  /** When true, wordmark only shows if showWordmark is also true (used by expanded rail). */
  compact?: boolean
}

export function MatchViewLogo({
  className = '',
  showWordmark = true,
  variant = 'default',
  compact = false,
}: MatchViewLogoProps) {
  const isRail = variant === 'rail'
  const showTitle = showWordmark && !compact

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <img
        src={matchViewLogo}
        alt=""
        className="h-8 w-auto shrink-0"
        aria-hidden="true"
      />
      {showTitle ? (
        <div className="min-w-0">
          <p
            className={`truncate text-sm font-bold leading-tight ${
              isRail ? 'text-rail-text-primary' : 'text-text-primary'
            }`}
          >
            MatchView
          </p>
          {!isRail ? (
            <p className="truncate text-xs text-text-secondary">Experimentation Platform</p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
