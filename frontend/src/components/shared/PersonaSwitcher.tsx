import { ArrowLeftRight, Briefcase, FlaskConical } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import type { Persona } from '../../context/types'
import { AppIcon } from './AppIcon'

interface PersonaSwitcherProps {
  variant?: 'default' | 'rail'
}

export function PersonaSwitcher({ variant = 'default' }: PersonaSwitcherProps) {
  const { currentPersona, setPersona } = useMatchView()

  const toggle = () => {
    const next: Persona = currentPersona === 'executive' ? 'analyst' : 'executive'
    setPersona(next)
  }

  const isRail = variant === 'rail'

  return (
    <button
      type="button"
      onClick={toggle}
      className={`flex w-full items-center justify-center gap-2 rounded-xs border px-3 py-2 text-xs font-medium transition-colors duration-instant ${
        isRail
          ? 'focus-ring-rail border-rail-border/50 bg-rail-raised text-rail-text-primary hover:border-rail-border hover:bg-rail-hover'
          : 'focus-ring border-border-muted/40 bg-surface-raised text-text-primary hover:border-border-muted hover:shadow-glow'
      }`}
      aria-label={`Switch persona. Current: ${currentPersona}`}
    >
      <span
        className={`flex items-center gap-1 ${currentPersona === 'executive' ? 'opacity-100' : 'opacity-40'}`}
      >
        <AppIcon icon={Briefcase} size="xs" />
        Exec
      </span>
      <AppIcon
        icon={ArrowLeftRight}
        size="xs"
        className={isRail ? 'text-rail-text-secondary' : 'text-text-secondary'}
      />
      <span
        className={`flex items-center gap-1 ${currentPersona === 'analyst' ? 'opacity-100' : 'opacity-40'}`}
      >
        <AppIcon icon={FlaskConical} size="xs" />
        Analyst
      </span>
    </button>
  )
}
