import { LogOut } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import { PersonaSwitcher } from '../shared/PersonaSwitcher'

interface RailUserFooterProps {
  expanded: boolean
}

export function RailUserFooter({ expanded }: RailUserFooterProps) {
  const { currentUser, logout } = useMatchView()

  if (!currentUser) return null

  return (
    <div className={`flex flex-col gap-2 ${expanded ? '' : 'items-center'}`}>
      {expanded && <PersonaSwitcher variant="rail" />}

      {expanded && (
        <button
          type="button"
          onClick={logout}
          className="focus-ring-rail flex w-full items-center justify-center gap-1.5 rounded-xs border border-rail-border/30 bg-rail-base/40 px-2 py-1.5 text-xs font-medium text-rail-text-secondary transition-colors hover:border-rail-border/50 hover:bg-rail-hover hover:text-rail-text-primary"
        >
          <AppIcon icon={LogOut} size="xs" />
          Log out
        </button>
      )}

      <div
        className={`flex items-center gap-2 ${expanded ? 'rounded-xs px-1 py-1' : 'justify-center'}`}
      >
        <img
          src={currentUser.avatarUrl}
          alt=""
          className="h-9 w-9 shrink-0 rounded-full border-2 border-rail-border/40 bg-rail-raised object-cover"
        />
        {expanded && (
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-rail-text-primary">{currentUser.name}</p>
            <p className="truncate text-micro text-rail-text-secondary">{currentUser.email}</p>
          </div>
        )}
      </div>
    </div>
  )
}
